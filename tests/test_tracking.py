import copy
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
from src.applications import mark_applied, read_records
from src.verification import verify_job, deadline


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.item = {'id': '1', 'company': 'Example', 'title': 'Data Scientist', 'url': 'https://careers.example.com/jobs/1'}
        self.company = {'domains': ['careers.example.com']}

    def test_http_statuses_distinguish_closed_and_blocked(self):
        for code, expected in [(404, 'closed'), (410, 'closed'), (403, 'unverified'), (429, 'unverified'), (503, 'unverified')]:
            with patch('src.verification.fetch', side_effect=urllib.error.HTTPError(self.item['url'], code, 'test', {}, None)):
                self.assertEqual(verify_job(self.item, self.company)['availability']['status'], expected)

    def test_jsonld_deadline_and_identity(self):
        ld = {'@type': 'JobPosting', 'title': 'Data Scientist', 'description': 'Research role', 'validThrough': '2099-06-01'}
        body = '<script type="application/ld+json">' + json.dumps(ld) + '</script>'
        with patch('src.verification.fetch', return_value=(body, self.item['url'])):
            result = verify_job(self.item, self.company)
        self.assertEqual(result['availability']['status'], 'open')
        self.assertEqual(result['deadline']['date'], '2099-06-01')
        self.item['title'] = 'Accountant'
        with patch('src.verification.fetch', return_value=(body, self.item['url'])):
            self.assertEqual(verify_job(self.item, self.company)['availability']['status'], 'unverified')

    def test_expired_deadline_and_soft_404(self):
        for body in ['<p>This job is no longer available</p>', '<script type="application/ld+json">{"@type":"JobPosting","title":"Data Scientist","description":"Role","validThrough":"2020-01-01"}</script>']:
            with patch('src.verification.fetch', return_value=(body, self.item['url'])):
                self.assertEqual(verify_job(self.item, self.company)['availability']['status'], 'closed')

    def test_script_template_and_homepage_are_not_verified_jobs(self):
        with patch('src.verification.fetch', return_value=('<script>this job is no longer available</script>', 'https://careers.example.com/')):
            self.assertEqual(verify_job(self.item, self.company)['availability']['status'], 'unverified')

    def test_workday_detail_and_deadline(self):
        self.item['url'] = 'https://example.wd1.myworkdayjobs.com/en-US/Careers/job/US/Job_1'
        body = json.dumps({'jobPostingInfo': {'title': 'Data Scientist', 'jobDescription': 'Apply by June 1, 2099'}})
        with patch('src.verification.fetch', return_value=(body, self.item['url'])) as fetch:
            result = verify_job(self.item, {'domains': ['example.wd1.myworkdayjobs.com']})
        self.assertIn('/wday/cxs/example/Careers/job/US/Job_1', fetch.call_args.args[0])
        self.assertEqual(result['deadline']['date'], '2099-06-01')

    def test_unconfigured_url_is_not_fetched(self):
        with patch('urllib.request.build_opener') as opener:
            self.item['url'] = 'http://127.0.0.1/private'
            self.assertEqual(verify_job(self.item, self.company)['availability']['status'], 'unverified')
            opener.assert_not_called()


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = {}
        self.item = {'id': 'one', 'company': '=BAD()', 'title': 'Scientist', 'url': 'https://example.com/jobs/1', 'location': 'US', 'match': {'score': 8.2}, 'deadline': {'date': '2099-06-01'}}

    def test_toggle_is_durable_idempotent_and_preserves_other_sheet(self):
        first = mark_applied(self.base, self.config, self.item, True)
        path = self.base / 'applications.xlsx'
        wb = load_workbook(path)
        wb.create_sheet('Notes')['A1'] = 'Keep me'
        wb['Applications']['K1'] = 'My note'
        wb['Applications']['K2'] = 'Referral pending'
        wb.save(path); wb.close()
        mark_applied(self.base, self.config, self.item, True)
        mark_applied(self.base, self.config, self.item, False)
        record = read_records(self.base, self.config)['one']
        self.assertFalse(record['applied'])
        self.assertEqual(record['applied_at'], first['applied_at'])
        wb = load_workbook(path)
        self.assertEqual(wb['Applications'].max_row, 2)
        self.assertEqual(wb['Notes']['A1'].value, 'Keep me')
        self.assertEqual(wb['Applications']['K2'].value, 'Referral pending')
        self.assertEqual(wb['Applications']['B2'].data_type, 's')
        self.assertEqual(wb['Applications']['E2'].hyperlink.target, self.item['url'])
        wb.close()

    def test_export_failure_does_not_commit_checkbox(self):
        mark_applied(self.base, self.config, self.item, True)
        with patch('src.applications.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                mark_applied(self.base, self.config, self.item, False)
        self.assertTrue(read_records(self.base, self.config)['one']['applied'])

    def test_excel_open_lock_and_incompatible_sheet_are_preserved(self):
        mark_applied(self.base, self.config, self.item, True)
        lock = self.base / '~$applications.xlsx'; lock.touch()
        with self.assertRaises(ValueError):
            mark_applied(self.base, self.config, self.item, False)
        lock.unlink()
        wb = load_workbook(self.base / 'applications.xlsx'); wb['Applications']['A1'] = 'Existing unrelated table'; wb.save(self.base / 'applications.xlsx'); wb.close()
        with self.assertRaises(ValueError):
            mark_applied(self.base, self.config, self.item, False)


class DashboardAPITests(unittest.TestCase):
    def test_checkbox_roundtrip_and_csrf(self):
        import io
        from types import SimpleNamespace
        import career

        class Connection:
            def __init__(self, request):
                self.input = io.BytesIO(request)
                self.output = b''
            def makefile(self, *args):
                return self.input
            def sendall(self, data):
                self.output += data

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'output/fulltime').mkdir(parents=True)
            (base / 'output/fulltime/jobs.json').write_text(json.dumps({'jobs': [
                {'id': 'one', 'company': 'Example', 'title': 'Scientist', 'url': 'https://example.com/job/1'}]}))
            def request(method, payload=None, token=career.CSRF_TOKEN):
                body = json.dumps(payload).encode() if payload else b''
                route = ('/api/over-my-reach' if payload and 'over_my_reach' in payload else '/api/applied') if method == 'POST' else '/api/jobs'
                headers = f'{method} {route} HTTP/1.0\r\nHost: localhost:7777\r\nOrigin: http://localhost:7777\r\nX-CSRF-Token: {token}\r\nContent-Length: {len(body)}\r\n\r\n'
                conn = Connection(headers.encode() + body)
                with patch.object(career, 'BASE', base), patch.object(career.Handler, 'log_message'):
                    career.Handler(conn, ('127.0.0.1', 1), SimpleNamespace(server_port=7777, app_config={}))
                head, response = conn.output.split(b'\r\n\r\n', 1)
                return int(head.split()[1]), json.loads(response)
            self.assertEqual(request('POST', {'id': 'one', 'applied': True}, 'bad')[0], 403)
            self.assertFalse((base / 'applications.xlsx').exists())
            self.assertEqual(request('POST', {'id': 'missing', 'applied': True})[0], 404)
            self.assertEqual(request('POST', {'id': 'one', 'applied': True})[0], 200)
            self.assertTrue(request('GET')[1]['jobs'][0]['applied'])
            self.assertEqual(request('POST', {'id': 'one', 'applied': False})[0], 200)
            self.assertFalse(request('GET')[1]['jobs'][0]['applied'])
            self.assertIsNotNone(request('GET')[1]['jobs'][0]['applied_at'])
            self.assertEqual(request('POST', {'id': 'one', 'over_my_reach': True}, 'bad')[0], 403)
            self.assertEqual(request('POST', {'id': 'missing', 'over_my_reach': True})[0], 404)
            self.assertEqual(request('POST', {'id': 'one', 'over_my_reach': 'true'})[0], 409)
            self.assertEqual(request('POST', {'id': 'one', 'over_my_reach': True})[0], 200)
            state = request('GET')[1]['jobs'][0]
            self.assertTrue(state['over_my_reach'])
            self.assertFalse(state['applied'])
            self.assertEqual(request('POST', {'id': 'one', 'applied': True})[0], 200)
            self.assertTrue(request('GET')[1]['jobs'][0]['over_my_reach'])
            self.assertEqual(request('POST', {'id': 'one', 'over_my_reach': False})[0], 200)
            self.assertFalse(request('GET')[1]['jobs'][0]['over_my_reach'])
            self.assertTrue(request('GET')[1]['jobs'][0]['applied'])



if __name__ == '__main__':
    unittest.main()
