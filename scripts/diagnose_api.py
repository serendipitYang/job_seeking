"""Read-only API routing diagnostic. Never prints keys or authorization headers."""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from career import load_env

load_env()
request = urllib.request.Request('https://api.openai.com/v1/models', headers={
    'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
    'User-Agent': 'JobResearch/1.0'})
with urllib.request.urlopen(request, timeout=30) as response:
    body = json.load(response)
    diagnostic = {k: response.headers.get(k) for k in (
        'x-request-id', 'openai-organization', 'openai-project', 'openai-version')}
    diagnostic['status'] = response.status
    diagnostic['configured_model_listed'] = 'gpt-5.4-mini' in {m['id'] for m in body.get('data', [])}
    print(json.dumps(diagnostic, indent=2))
