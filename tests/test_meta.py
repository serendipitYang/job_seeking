import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.meta import details, collect, identity, operation_ids, OPERATIONS, fulltime_title
from src.verification import verify_job
from src.fulltime import filter_active_jobs

URL = 'https://www.metacareers.com/profile/job_details/123/'


def page(ident='123', country='US', employment='FULL_TIME'):
    data = {'@type':'JobPosting','title':'Research Scientist, AI (PhD)','description':'Research models',
            'qualifications':'PhD and Python','responsibilities':'Develop experiments',
            'hiringOrganization':{'name':'Meta'},'employmentType':employment,
            'jobLocation':[{'name':'Menlo Park, CA','address':{'addressCountry':country}}]}
    return '<link rel="canonical" href="https://www.metacareers.com/profile/job_details/'+ident+'/"><script type="application/ld+json">'+json.dumps(data)+'</script>'


class MetaTests(unittest.TestCase):
    def test_exact_identity_qualifications_and_country(self):
        info = details(page(), URL)
        self.assertEqual(info['countries'], ['US'])
        self.assertIn('PhD and Python',info['description'])
        self.assertEqual(identity('https://www.metacareers.com/jobs/123/?source=search'), '123')
        with self.assertRaises(ValueError): details(page('999'), URL)
        with self.assertRaises(ValueError): details(page().replace('qualifications','missing'), URL)
        with patch('src.verification.fetch',return_value=(page(),URL)):
            result=verify_job({'url':URL,'title':'Old title'},{'domains':['metacareers.com']})
        self.assertEqual(result['availability']['status'],'open')
        self.assertEqual(result['employment_type'],'FULL_TIME')

    def test_public_operation_ids_parsed_without_executing_scripts(self):
        raw=';'.join('__d("'+n+'_candidate_portalRelayOperation",[],function(a){a.exports="123456"})' for n in OPERATIONS)
        self.assertEqual(set(operation_ids(raw)),set(OPERATIONS))
        self.assertEqual(operation_ids('alert("do not execute")'),{})

    def test_full_catalog_count_and_filters(self):
        rows=[{'id':str(i),'title':title,'locations':[loc]} for i,title,loc in [
            (1,'Data Scientist','Menlo Park, CA'), (2,'Research Scientist Intern (PhD)','Seattle, WA'),
            (3,'Research Scientist','London, UK'),(4,'Research Scientist','Remote, US')]]
        with patch('src.meta.PublicSearch') as api:
            api.return_value.query.side_effect=[{'all_jobs':rows},{'job_count':4}]
            found,notes,coverage=collect({'name':'Meta'},{})
        self.assertEqual(len(found),2)
        self.assertTrue(coverage['complete'])
        self.assertEqual(notes,[])
        with patch('src.meta.PublicSearch') as api:
            api.return_value.query.side_effect=[{'all_jobs':rows},{'job_count':5}]
            _,notes,coverage=collect({'name':'Meta'},{})
        self.assertFalse(coverage['complete'])
        self.assertTrue(notes)

    def test_non_full_time_metadata_and_countries_removed(self):
        self.assertFalse(fulltime_title('Data Scientist STE 18 Month Contract'))
        self.assertTrue(fulltime_title('Data Scientist, Internal Analytics'))
        with tempfile.TemporaryDirectory() as directory:
            jobs={'a':{'id':'a','company':'Meta',**details(page(employment='INTERN'),URL)},
                  'b':{'id':'b','company':'Meta',**details(page(country='GB'),URL)}}
            filter_active_jobs(jobs,Path(directory))
            self.assertEqual(jobs,{})
            self.assertIn('a',json.loads((Path(directory)/'excluded_employment.json').read_text()))
            self.assertIn('b',json.loads((Path(directory)/'excluded_non_us.json').read_text()))

    def test_missing_or_malformed_catalog_is_not_empty_success(self):
        with patch('src.meta.PublicSearch') as api:
            api.return_value.query.side_effect=[{'all_jobs':None},{'job_count':4}]
            with self.assertRaises(ValueError):collect({'name':'Meta'},{})
        with patch('src.meta.PublicSearch') as api:
            api.return_value.query.side_effect=[{'all_jobs':[]},{'job_count':0}]
            with self.assertRaises(ValueError):collect({'name':'Meta'},{})
