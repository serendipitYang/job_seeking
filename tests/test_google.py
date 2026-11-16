import json
import unittest
from unittest.mock import patch
from src.google import blocks, candidate, collect, details, identity, search_page, JobNotFound, fulltime_title
from src.verification import verify_job

ROOT = 'https://www.google.com/about/careers/applications/'


def row(number='123', title='Research Data Scientist', country='US'):
    r = [None] * 21
    r[0:3] = [number, title, ROOT + 'signin?jobId=test']
    r[3] = [None, '<p>Research responsibilities</p>']
    r[4] = [None, '<p>PhD or equivalent research experience</p>']
    r[7] = 'Google'
    r[9] = [['Mountain View, CA, USA' if country == 'US' else 'London, UK', [], '', '', '', country]]
    r[10] = [None, '<p>Develop research and data science systems.</p>']
    r[15] = [None, 'Sponsorship information']
    return r


def block(key, data):
    return '<script>AF_initDataCallback({key: ' + repr(key) + ", hash: '1', data:" + json.dumps(data) + ', sideChannel:{}});</script>'


def search(rows, total, n=1, size=20):
    return block('ds:1', [rows, None, total, size]) + ''.join('<a href="jobs/results/' + r[0] + '-role?q=Data">Role</a>' for r in rows) + (f'Showing {(n-1)*size+1} to {(n-1)*size+len(rows)} of {total} rows' if rows else '')


class GoogleTests(unittest.TestCase):
    def test_exact_selected_job_required(self):
        url = ROOT + 'jobs/results/123-role'
        raw = block('ds:0', [row()]) + search([row('999')], 1)
        info = details(raw, url)
        self.assertEqual(info['countries'], ['US'])
        self.assertIn('PhD', info['description'])
        self.assertIn('Sponsorship', info['description'])
        with self.assertRaises(ValueError):
            details(raw, url.replace('123', '999'))
        with self.assertRaises(ValueError):
            details(search([row()], 1), url)
        with patch('src.verification.fetch', return_value=(raw, url)):
            self.assertEqual(verify_job({'url':url,'title':'Old title'}, {'domains':['google.com']})['availability']['status'],'open')

    def test_expired_selected_job_does_not_use_surrounding_results(self):
        url = ROOT + 'jobs/results/123-role'
        raw = block('ds:0', [None]) + search([row()], 1) + '<h2>Job not found.</h2><p>This job may have been taken down.</p>'
        with self.assertRaises(JobNotFound):
            details(raw, url)
        with patch('src.verification.fetch', return_value=(raw,url)):
            self.assertEqual(verify_job({'url':url,'title':'Research Data Scientist'}, {'domains':['google.com']})['availability']['status'],'closed')

    def test_schema_pagination_and_job_identity(self):
        with self.assertRaises(ValueError):
            search_page(search([row()], 40), 2)
        with self.assertRaises(ValueError):
            search_page(search([], 40), 1)
        self.assertEqual(search_page(search([],0),1)[1],0)
        with self.assertRaises(ValueError):
            blocks('<script>alert(1)</script>')
        self.assertEqual(identity(ROOT+'jobs/results/123-changed-slug?q=AI'), '123')
        self.assertIsNone(identity('https://evil.example/jobs/results/123-role'))

    def test_candidates_include_phd_and_ai_engineering_not_interns_or_facilities(self):
        self.assertTrue(candidate('Software Engineer III',['PhD']))
        self.assertTrue(candidate('Software Engineer',['AI'],'Develop machine learning models'))
        self.assertTrue(candidate('Research Data Scientist',['Data']))
        self.assertFalse(candidate('Research Data Scientist Intern, PhD, Summer 2027',['PhD']))
        self.assertFalse(candidate('Data Center Facilities Technician',['Data']))
        self.assertFalse(candidate('Air Conditioning Technician',['AI']))
        self.assertFalse(candidate('Student Researcher, PhD, Winter-Summer 2027',['PhD']))
        self.assertTrue(fulltime_title('Software Engineer III, Database Internals'))

    def test_queries_paginate_deduplicate_and_filter_foreign_interns(self):
        from urllib.parse import urlsplit, parse_qs
        def fetch(url, domains):
            p=parse_qs(urlsplit(url).query);n=int(p['page'][0])
            rows=[row(),row('124','Data Scientist Intern')] if n==1 else [row('125',country='GB')]
            return search(rows,3,n,size=2),url
        company={'name':'Google','domains':['google.com'],'queries':['Data','PhD']}
        cfg={'collection':{'google_max_pages_per_query':2}}
        with patch('src.verification.fetch',side_effect=fetch):
            found,notes,coverage=collect(company,cfg)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['discovery_queries'],['Data','PhD'])
        self.assertTrue(coverage['complete'])
        self.assertEqual(coverage['unique_listings'],3)
        self.assertEqual(coverage['listings_seen'],6)
        cfg['collection']['google_max_pages_per_query']=1
        with patch('src.verification.fetch',side_effect=fetch):
            _,notes,coverage=collect(company,cfg)
        self.assertFalse(coverage['complete'])
        self.assertTrue(notes)

    def test_existing_student_roles_are_archived(self):
        import tempfile
        from pathlib import Path
        from src.fulltime import filter_active_jobs
        with tempfile.TemporaryDirectory() as directory:
            jobs = {'old': {'id':'old','company':'Google','title':'Student Researcher, PhD, 2027','location':'US'}}
            filter_active_jobs(jobs, Path(directory))
            self.assertEqual(jobs, {})
            self.assertIn('old', json.loads((Path(directory)/'excluded_employment.json').read_text()))

    def test_failed_page_reports_partial_not_exhaustive(self):
        def fetch(url,domains):
            if 'page=2' in url:raise OSError('offline')
            return search([row()],2,size=1),url
        with patch('src.verification.fetch',side_effect=fetch),patch('src.google.time.sleep'):
            found,notes,coverage=collect({'name':'Google','domains':['google.com'],'queries':['Data']},{'collection':{'google_max_pages_per_query':2}})
        self.assertEqual(len(found),1)
        self.assertFalse(coverage['complete'])
        self.assertIn('offline',notes[0])
