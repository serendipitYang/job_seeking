import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.fulltime import (APIRequestError, DIMENSIONS, NightlyBudget, location_fit, OpenAIClient, collect_api, fingerprint,
                          job, relevant, update)

BASE = Path(__file__).resolve().parents[1]


class FulltimeTests(unittest.TestCase):
    def setUp(self):
        verifier = patch('src.fulltime.verify_jobs')
        verifier.start()
        self.addCleanup(verifier.stop)
        apple = patch('src.apple.collect', return_value=([], [], {'complete': True}))
        apple.start()
        self.addCleanup(apple.stop)
        google = patch('src.google.collect', return_value=([], [], {'complete': True}))
        google.start()
        self.addCleanup(google.stop)
        meta = patch('src.meta.collect', return_value=([], [], {'complete': True}))
        meta.start()
        self.addCleanup(meta.stop)
        self.config = json.loads((BASE / "fulltime.example.json").read_text())
        self.item = job("NVIDIA", "Senior Data Scientist", "US", "https://example.com/job/1",
                        "PhD or equivalent research experience. " * 10, "workday", "1")

    def test_fulltime_not_limited_to_new_grads(self):
        for title in ["Senior Data Scientist", "Data Scientist II", "Research Scientist, New PhD", "Internal Medicine Data Scientist"]:
            self.assertTrue(relevant(title, self.config["keywords"]), title)
        for title in ["Data Science Intern", "Machine Learning Co-op", "Data Scientist Internship"]:
            self.assertFalse(relevant(title, self.config["keywords"]), title)

    def test_cache_invalidates_resume_preferences_model_and_jd(self):
        key = fingerprint(self.item, "resume", self.config)
        self.assertNotEqual(key, fingerprint(self.item, "new resume", self.config))
        for changed in ["preferences", "llm"]:
            cfg = copy.deepcopy(self.config)
            cfg[changed]["model" if changed == "llm" else "sponsorship_required"] = "changed"
            self.assertNotEqual(key, fingerprint(self.item, "resume", cfg))
        self.item["description"] += " industry mandatory"
        self.assertNotEqual(key, fingerprint(self.item, "resume", self.config))

    def test_exclusion_needs_actual_jd_evidence(self):
        client = OpenAIClient(self.config["llm"])
        result = dict(dimensions={k: 8 for k in DIMENSIONS}, eligibility="excluded", unknowns=[], exclusion_quote="No new graduates")
        with patch.object(client, "response", return_value=(result, {})):
            score = client.score(self.item, "resume", {})
        self.assertEqual(score["eligibility"], "uncertain")
        self.assertEqual(score["score"], 8)

    def test_workday_pagination_and_detail_links(self):
        company = self.config["companies"][2]
        responses = [{"total": 21, "jobPostings": [{"title": "Senior Data Scientist", "externalPath": "/job/US/DS_1"}]},
                     {"jobPostingInfo": {"jobDescription": "<p>PhD research counts</p>", "jobReqId": "1", "timeType": "Full time"}},
                     {"total": 0, "jobPostings": []}]
        with patch("src.fulltime.request_json", side_effect=responses) as req, patch("src.fulltime.time.sleep"):
            jobs, notes = collect_api(company, self.config)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["description"], "PhD research counts")
        self.assertIn("/en-US/NVIDIAExternalCareerSite/job/", jobs[0]["url"])
        self.assertEqual(req.call_args_list[2].args[1]["offset"], 20)
        self.assertFalse(notes)

    def test_foreign_jobs_do_not_consume_us_collection_limit(self):
        self.config['collection']['max_jobs_per_company'] = 1
        responses = [
            {'total': 2, 'jobPostings': [
                {'title': 'Data Scientist', 'externalPath': '/job/India/1'},
                {'title': 'Data Scientist', 'externalPath': '/job/US/2'}]},
            {'jobPostingInfo': {'jobDescription': 'Research', 'location': 'India - Hyderabad', 'jobReqId': '1'}},
            {'jobPostingInfo': {'jobDescription': 'Research', 'location': 'US, CA, Santa Clara', 'jobReqId': '2'}}]
        with patch('src.fulltime.request_json', side_effect=responses), patch('src.fulltime.time.sleep'):
            found, notes = collect_api(self.config['companies'][2], self.config)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['location'], 'US, CA, Santa Clara')

    def test_workday_zero_total_on_later_pages_does_not_stop_early(self):
        rows = [{"title": "Sales", "externalPath": "/unused"}] * 20
        responses = [{"total": 45, "jobPostings": rows}, {"total": 0, "jobPostings": rows},
                     {"total": 0, "jobPostings": []}]
        with patch("src.fulltime.request_json", side_effect=responses) as req, patch("src.fulltime.time.sleep"):
            collect_api(self.config["companies"][2], self.config)
        self.assertEqual(req.call_count, 3)

    def test_failure_preserves_old_job_marks_stale_and_invalidates_score(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            out = base / "output/fulltime"
            out.mkdir(parents=True)
            item = {**self.item, "match": {"score": 9}}
            (out / "jobs.json").write_text(json.dumps({"jobs": [item]}))
            self.config["companies"] = [self.config["companies"][2]]
            with patch("src.fulltime.resume_text", return_value="new resume"), patch("src.fulltime.collect_api", side_effect=RuntimeError("offline")):
                result = update(self.config, base)
            self.assertEqual(result["companies"][0]["status"], "error")
            self.assertEqual(len(result["jobs"]), 1)
            self.assertTrue(result["jobs"][0]["stale"])
            self.assertIsNone(result["jobs"][0]["match"])

    def test_search_rejects_unattributed_and_foreign_urls(self):
        client = OpenAIClient(self.config["llm"])
        rows = [{"title": "Data Scientist", "location": "US", "description": "x" * 250, "url": u} for u in
                ["https://jobs.apple.com/job/1", "https://evil.example/job/2", "https://jobs.apple.com/job/3"]]
        raw = {"output": [{"action": {"sources": [{"url": r["url"]} for r in rows[:2]]}}]}
        with patch.object(client, "response", return_value=({"jobs": rows}, raw)):
            jobs = client.search(self.config["companies"][0], self.config)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["url"], rows[0]["url"])

    def test_call_cap_prevents_network_request(self):
        cfg = {**self.config["llm"], "max_scores_per_run": 0}
        with patch("src.fulltime.request_json") as req:
            with self.assertRaises(RuntimeError):
                OpenAIClient(cfg).response("test", {})
            req.assert_not_called()

    def test_location_exclusion_and_alternatives(self):
        prefs = {"excluded_locations": ["New York"]}
        for loc in ["New York, NY", "Albany, NY", "Brooklyn"]:
            self.assertEqual(location_fit(loc, prefs), "excluded_location")
        self.assertEqual(location_fit("New York / Seattle, WA", prefs), "preferred_alternative")
        self.assertEqual(location_fit("New York / Boston, MA", prefs), "review_location")
        self.assertEqual(location_fit("Remote - New York", prefs), "review_location")
        self.assertEqual(location_fit("Minneapolis, MN", prefs), "preferred")

    def test_budget_persists_across_runs_and_preserves_failed_reservation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "budget.json"
            budget = NightlyBudget(path, .4)
            budget.reserve("gpt-5.4-mini", 2200, False)
            with self.assertRaises(RuntimeError):
                NightlyBudget(path, .4).reserve("gpt-5.4-mini", 2200, False)

    def test_budget_settles_known_usage_and_rejects_unknown_model(self):
        with tempfile.TemporaryDirectory() as temp:
            budget = NightlyBudget(Path(temp) / "budget.json", .4)
            reservation = budget.reserve("gpt-5.4-mini", 2200, False)
            budget.settle(reservation, {"usage": {"input_tokens": 1000, "output_tokens": 100}, "output": []})
            self.assertEqual(json.loads(budget.path.read_text())[budget.window_key], 1200)
            budget.reserve("gpt-5.4-mini", 2200, False)
            with self.assertRaises(ValueError):
                budget.reserve("unknown-expensive-model", 2200, False)

    def test_quota_rejection_releases_reservation(self):
        with tempfile.TemporaryDirectory() as temp:
            budget = NightlyBudget(Path(temp) / "budget.json")
            client = OpenAIClient(self.config["llm"], budget)
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), patch('src.fulltime.request_json', side_effect=APIRequestError(429, 'credit_balance_exhausted', 'No credits')):
                with self.assertRaises(APIRequestError):
                    client.response('test', {})
            self.assertEqual(json.loads(budget.path.read_text())[budget.window_key], 0)

    def test_score_only_reuses_saved_jobs_without_collection(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'output/fulltime'
            out.mkdir(parents=True)
            item = {**self.item, 'stale': False, 'last_seen': '2026-09-19'}
            (out / 'jobs.json').write_text(json.dumps({'jobs': [item], 'companies': []}))
            with patch('src.fulltime.resume_text', return_value='resume'), patch('src.fulltime.collect_api') as collect, patch.object(OpenAIClient, 'search') as search:
                result = update(self.config, Path(temp), score_only=True)
            collect.assert_not_called()
            search.assert_not_called()
            self.assertEqual(result['jobs'][0]['last_seen'], '2026-09-19')
            self.assertFalse(result['jobs'][0]['stale'])

    def test_targeted_update_preserves_other_companies_and_freshness(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'output/fulltime'
            out.mkdir(parents=True)
            item = {**self.item, 'stale': False, 'last_seen': '2026-09-19'}
            old_status = {'company': 'NVIDIA', 'status': 'ok', 'checked_at': 'old', 'notes': []}
            (out / 'jobs.json').write_text(json.dumps({'jobs': [item], 'companies': [old_status]}))
            with patch('src.fulltime.resume_text', return_value='resume'), patch('src.fulltime.collect_api') as collect:
                result = update(self.config, Path(temp), only_companies=['Apple'])
            collect.assert_not_called()
            self.assertFalse(result['jobs'][0]['stale'])
            self.assertEqual(result['jobs'][0]['last_seen'], '2026-09-19')
            self.assertIn(old_status, result['companies'])

    def test_non_us_archived_even_during_targeted_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            out = base / 'output/fulltime'
            out.mkdir(parents=True)
            foreign = {**self.item, 'id': 'foreign', 'location': 'India - Hyderabad'}
            (out / 'jobs.json').write_text(json.dumps({'jobs': [self.item, foreign], 'companies': []}))
            with patch('src.fulltime.resume_text', return_value='resume'):
                result = update(self.config, base, only_companies=['Apple'], verify_only=True)
            self.assertEqual([j['id'] for j in result['jobs']], [self.item['id']])
            self.assertEqual(json.loads((out / 'excluded_non_us.json').read_text())['foreign']['location'], 'India - Hyderabad')

    def test_google_canonical_id_preserves_application_record_key(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            out = base / 'output/fulltime'
            out.mkdir(parents=True)
            old = {**self.item, 'company': 'Google', 'id': 'existing-application-id', 'url': 'https://careers.google.com/jobs/results/123-old-title?q=Data'}
            fresh = {**old, 'id': 'new-id', 'url': 'https://www.google.com/about/careers/applications/jobs/results/123-updated-title'}
            (out / 'jobs.json').write_text(json.dumps({'jobs': [old]}))
            with patch('src.fulltime.resume_text', return_value='resume'), patch('src.google.collect', return_value=([fresh], [], {'complete': True})):
                result = update(self.config, base, only_companies=['Google'])
            self.assertEqual(len(result['jobs']), 1)
            self.assertEqual(result['jobs'][0]['id'], old['id'])
            self.assertEqual(result['jobs'][0]['url'], fresh['url'])

    def test_meta_url_alias_preserves_feedback_record_key(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            out = base / 'output/fulltime'
            out.mkdir(parents=True)
            old = {**self.item, 'company': 'Meta', 'id': 'feedback-record-id', 'url': 'https://www.metacareers.com/jobs/123/'}
            fresh = {**old, 'id': 'new-id', 'url': 'https://www.metacareers.com/profile/job_details/123/'}
            (out / 'jobs.json').write_text(json.dumps({'jobs': [old]}))
            with patch('src.fulltime.resume_text', return_value='resume'), patch('src.meta.collect', return_value=([fresh], [], {'complete': True})):
                result = update(self.config, base, only_companies=['Meta'])
            self.assertEqual(len(result['jobs']), 1)
            self.assertEqual(result['jobs'][0]['id'], old['id'])

    def test_unknown_target_company_fails_before_network(self):
        with self.assertRaises(ValueError):
            update(self.config, BASE, only_companies=['Typo'])

    def test_quota_failure_stops_other_ai_requests_but_keeps_collection(self):
        with tempfile.TemporaryDirectory() as temp:
            config = copy.deepcopy(self.config)
            config['companies'] = config['companies'][:3]
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), patch('src.fulltime.resume_text', return_value='resume'), patch.object(OpenAIClient,'search',side_effect=APIRequestError(429,'credit_balance_exhausted','No credits')) as search, patch.object(OpenAIClient,'score') as score, patch('src.fulltime.collect_api',return_value=([self.item],[])) as collect:
                result = update(config, Path(temp), use_ai=True)
            self.assertEqual(search.call_count, 1)
            score.assert_not_called()
            collect.assert_called_once()
            self.assertEqual(len(result['jobs']), 1)


if __name__ == "__main__":
    unittest.main()
