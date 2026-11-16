#!/usr/bin/env python3
"""Local full-time job dashboard and nightly updater (Python 3.9+)."""
import argparse
import json
import os
import shlex
import sys
import secrets
from zipfile import BadZipFile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from src.fulltime import load_json, update, OpenAIClient, NightlyBudget, resume_text
from src.applications import read_records, mark_applied, settings as application_settings

from src import reach_feedback

BASE = Path(__file__).resolve().parent
CSRF_TOKEN = secrets.token_urlsafe(32)


def load_env():
    """Small literal .env loader: never execute shell content or print secrets."""
    path = BASE / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(json.dumps(value).encode())

    def do_POST(self):
        host = self.headers.get('Host', '')
        if host not in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'} or self.headers.get('Origin') != 'http://' + host or not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), CSRF_TOKEN):
            self.send_json({'error': 'Request origin or token is invalid; reload the dashboard'}, 403)
            return
        route = urlsplit(self.path).path
        field = 'over_my_reach' if route == '/api/over-my-reach' else 'applied'
        if route not in ('/api/applied', '/api/over-my-reach'):
            self.send_json({'error': 'Not found'}, 404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2048:
                raise ValueError('Invalid request size')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or type(payload.get(field)) is not bool:
                raise ValueError(field + ' must be a boolean')
            jobs = load_json(BASE / 'output/fulltime/jobs.json', {'jobs': []})['jobs']
            item = next((j for j in jobs if j['id'] == payload.get('id')), None)
            if item is None:
                self.send_json({'error': 'Job not found; reload results'}, 404)
                return
            record = (reach_feedback.mark(BASE, item, payload[field]) if field == 'over_my_reach'
                      else mark_applied(BASE, self.server.app_config, item, payload[field]))
            self.send_json({'id': item['id'], **record})
        except (ValueError, OSError, ImportError, BadZipFile) as exc:
            self.send_json({'error': str(exc)}, 409)

    def do_GET(self):
        # Explicit routes only: never serve the repository or resume files.
        if self.headers.get("Host", "").split(":")[0] not in {"127.0.0.1", "localhost"}:
            self.send_error(403)
            return
        route = urlsplit(self.path).path
        if route == "/api/jobs":
            value = load_json(BASE / "output/fulltime/jobs.json", {"jobs": [], "companies": [], "updated_at": None})
            value['csrf_token'] = CSRF_TOKEN
            value['applications_workbook'] = str(application_settings(BASE, self.server.app_config)[0])
            try:
                records = read_records(BASE, self.server.app_config)
                for item in value['jobs']:
                    item.update(records.get(item['id'], {'applied': False}))
            except Exception as exc:
                value['application_error'] = str(exc)
            value['reach_feedback_file'] = str(reach_feedback.path_for(BASE))
            try:
                records = reach_feedback.read_records(BASE)
                for item in value['jobs']:
                    item.update(records.get(item['id'], {'over_my_reach': False}))
            except Exception as exc:
                value['reach_error'] = str(exc)
            data, mime = json.dumps(value).encode(), "application/json"
        elif route == "/":
            data, mime = (BASE / "dashboard/index.html").read_bytes(), "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["update", "match", "verify", "serve", "cron", "probe"])
    parser.add_argument("--config", default="fulltime.local.json")
    parser.add_argument("--ai", action="store_true", help="Enable paid OpenAI search and scoring")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--company", action="append", help="Update only this exact company name; repeat for multiple companies")
    args = parser.parse_args()
    load_env()
    config_path = BASE / args.config
    if not config_path.exists():
        if args.config != "fulltime.local.json":
            parser.error("Config does not exist: " + str(config_path))
        config_path = BASE / "fulltime.example.json"
    if args.command == "serve":
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
        server.app_config = json.loads(config_path.read_text())
        print(f"Dashboard: http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    elif args.command == "cron":
        command = [sys.executable, str(BASE / "career.py"), "update", "--config", str(config_path)]
        if args.ai:
            command.append("--ai")
        # Cron treats % specially even inside shell quotes.
        line = shlex.join(command) + " >> " + shlex.quote(str(BASE / "output/nightly.log")) + " 2>&1"
        (BASE / "output").mkdir(exist_ok=True)
        print("0 2 * * * " + line.replace("%", "\\%"))
    elif args.command == "probe":
        config = json.loads(config_path.read_text())
        client = OpenAIClient(config["llm"], NightlyBudget(BASE / "output/fulltime/budget.json", config["llm"].get("nightly_budget_usd", 8)))
        result, _ = client.response("Return status OK.", {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"], "additionalProperties": False})
        print("API probe:", result)
    else:
        result = update(json.loads(config_path.read_text()), BASE, args.command != 'verify' and (args.ai or args.command == "match"), score_only=args.command == "match", only_companies=args.company, verify_only=args.command == 'verify')
        print(f"Saved {len(result['jobs'])} jobs; source status:")
        for company in result["companies"]:
            print(f"  {company['company']}: {company['status']} ({company['jobs_found']})")
        print("Usage: " + json.dumps(result["usage"]))


if __name__ == "__main__":
    main()
