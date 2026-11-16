import unittest
from unittest.mock import patch
from src.amazon_microsoft import collect, details, identity, normalize, seniority_priority, fulltime


def row(ident=1, country='United States', title='Data Scientist'):
    return dict(id=ident,name=title,locations=[country+', Washington, Redmond'],positionUrl='/careers/job/'+str(ident))


class EmployerTests(unittest.TestCase):
    def test_identity_and_seniority(self):
        self.assertEqual(identity('https://amazon.jobs/en/jobs/123/name'),identity('https://www.amazon.jobs/en/jobs/123/other'))
        self.assertIsNone(identity('https://evil.example/en/jobs/123'))
        self.assertEqual(seniority_priority({'title':'Data Scientist II'}),0)
        self.assertEqual(seniority_priority({'title':'Senior Applied Scientist'}),1)
        self.assertEqual(seniority_priority({'title':'Principal Research Scientist'}),2)
        self.assertTrue(fulltime({'title':'Senior Applied Scientist'}))
        self.assertFalse(fulltime({'title':'Research Intern'}))
        self.assertFalse(fulltime({'title':'Data Scientist','employment_type':'Part-Time'}))

    @patch('src.amazon_microsoft.time.sleep')
    @patch('src.amazon_microsoft.read_json')
    def test_pagination_and_country(self, read, sleep):
        read.side_effect = [dict(status=200,data=dict(count=2,positions=[row()])),dict(status=200,data=dict(count=2,positions=[row(2,'India')]))]
        jobs,notes,cov=collect(dict(name='Microsoft',type='microsoft',queries=['Data Scientist'],domains=['apply.careers.microsoft.com']),dict(keywords=['data scien']))
        self.assertEqual(len(jobs),1);self.assertTrue(cov['complete']);self.assertEqual(cov['unique_listings'],2)
        self.assertIn('start=1',read.call_args[0][0])

    @patch('src.amazon_microsoft.time.sleep')
    @patch('src.amazon_microsoft.read_json')
    def test_repeated_page_partial(self,read,sleep):
        read.return_value=dict(status=200,data=dict(count=2,positions=[row()]))
        _,notes,cov=collect(dict(name='Microsoft',type='microsoft',queries=['Data Scientist'],domains=[]),dict(keywords=['data scien']))
        self.assertFalse(cov['complete']);self.assertTrue(notes);self.assertEqual(read.call_count,2)

    @patch('src.amazon_microsoft.read_json')
    def test_details_reject_wrong_id(self,read):
        read.return_value=dict(status=200,data={**row(2),'jobDescription':'a'*400})
        with self.assertRaises(ValueError):details('https://apply.careers.microsoft.com/careers/job/1',['apply.careers.microsoft.com'])
        read.return_value=dict(status=200,data={**row(),'jobDescription':'a'*400,'efcustomTextEmploymentType':['Full-Time']})
        info=details('https://apply.careers.microsoft.com/careers/job/1',['apply.careers.microsoft.com'])
        self.assertEqual(info['countries'],['United States'])

    @patch('src.verification.fetch')
    def test_amazon_exact_application_and_fresh_jd(self,fetch):
        url='https://www.amazon.jobs/en/jobs/123/test'
        raw='<meta property="og:url" content="'+url+'"><h1>Data Scientist</h1><a href="https://www.amazon.jobs/applicant/jobs/123/apply">Apply</a>'
        raw+=''.join('<div><h2>'+s+'</h2><p>'+('Current qualifications. '*20)+'</p></div>' for s in ('Description','Basic Qualifications','Preferred Qualifications'))
        fetch.return_value=(raw,url)
        self.assertIn('Current qualifications',details(url,['amazon.jobs'])['description'])
        fetch.return_value=(raw.replace('/jobs/123/apply','/jobs/999/apply'),url)
        with self.assertRaises(ValueError):details(url,['amazon.jobs'])

if __name__=='__main__':unittest.main()
