import json
import unittest
from unittest.mock import patch
from src.apple import hydration, details, collect
from src.geography import country_scope
from src.verification import verify_job


def html(data):
    return '<script>window.__staticRouterHydrationData = JSON.parse(' + json.dumps(json.dumps({'loaderData': data})) + ');</script>'


class AppleTests(unittest.TestCase):
    def test_structured_detail_identity_location_and_requirements(self):
        url = 'https://jobs.apple.com/en-gb/details/123-456/scientist'
        data = {'jobDetails': {'jobsData': {'jobNumber': '123-456', 'postingTitle': 'Data Scientist', 'description': 'Research', 'minimumQualifications': 'PhD preferred', 'transformedPostingTitle': 'data-scientist', 'locations': [{'city': 'Cupertino', 'countryName': 'United States', 'countryID': 'iso-country-USA'}]}}}
        with patch('src.verification.fetch', return_value=(html(data), url)):
            result = verify_job({'url': url, 'title': 'Outdated title'}, {'domains': ['jobs.apple.com']})
        self.assertEqual(result['availability']['status'], 'open')
        self.assertEqual(result['countries'], ['USA'])
        self.assertIn('PhD preferred', result['description'])
        self.assertIn('/en-us/', result['url'])
        with self.assertRaises(ValueError):
            details(html(data), url.replace('123-456', '999'))
        with self.assertRaises(ValueError):
            hydration('<script>alert(1)</script>')

    def test_pagination_deduplication_and_complete_scope(self):
        rows = [{'id': str(i), 'postingTitle': title, 'transformedPostingTitle': 'role', 'locations': [{'countryID': country}]} for i,title,country in [(1,'Data Scientist','iso-country-USA'), (2,'Intern Data Scientist','iso-country-USA'), (3,'Data Scientist','iso-country-GBR')]]
        def fetch(url, domains):
            n = 2 if 'page=2' in url else 1
            return html({'search': {'page': n, 'totalRecords': 3, 'searchResults': rows[:2] if n == 1 else rows[2:]}}), url
        config = {'collection': {'apple_max_pages': 3}, 'keywords': ['data scien']}
        with patch('src.verification.fetch', side_effect=fetch):
            found, notes, coverage = collect({'name': 'Apple', 'domains': ['jobs.apple.com']}, config)
        self.assertEqual(len(found), 1)
        self.assertEqual(notes, [])
        self.assertTrue(coverage['complete'])
        self.assertEqual(coverage['pages_checked'], 2)
        config['collection']['apple_max_pages'] = 1
        with patch('src.verification.fetch', side_effect=fetch):
            _, notes, coverage = collect({'name': 'Apple', 'domains': ['jobs.apple.com']}, config)
        self.assertFalse(coverage['complete'])
        self.assertTrue(notes)

    def test_empty_page_retries_alternate_url_and_includes_seed(self):
        row = lambda n: {'id': str(n), 'postingTitle': 'Data Scientist', 'transformedPostingTitle': 'role', 'locations': [{'countryID': 'iso-country-USA'}]}
        visited = []
        def fetch(url, domains):
            visited.append(url)
            if '/details/' in url:
                return html({'jobDetails': {'jobsData': {'jobNumber': '3', 'postingTitle': 'Data Scientist', 'description': 'Research', 'transformedPostingTitle': 'role', 'locations': [{'countryID': 'iso-country-USA'}]}}}), url
            n = 2 if 'page=2' in url else 1
            rows = [] if '&page=2' in url else [row(n)]
            return html({'search': {'page': n, 'totalRecords': 2, 'searchResults': rows}}), url
        company = {'name':'Apple', 'domains':['jobs.apple.com'], 'seed_urls':['https://jobs.apple.com/en-us/details/3/role']}
        with patch('src.verification.fetch', side_effect=fetch), patch('src.apple.time.sleep'):
            found, notes, coverage = collect(company, {'collection': {'apple_max_pages': 3}, 'keywords': ['data scien']})
        self.assertTrue(coverage['complete'])
        self.assertEqual(len(found), 3)
        self.assertTrue(any('?page=2&location=' in url for url in visited))
        self.assertEqual(found[-1]['source'], 'apple_seed')
        self.assertEqual(notes, [])

    def test_empty_or_repeated_pages_are_not_exhaustive(self):
        company = {'name':'Apple','domains':['jobs.apple.com']}
        config = {'collection':{'apple_max_pages':3},'keywords':['data scien']}
        data = {'search':{'page':1,'totalRecords':0,'searchResults':[]}}
        with patch('src.verification.fetch', return_value=(html(data), '')):
            with self.assertRaises(ValueError):
                collect(company, config)
        row = {'id':'1','postingTitle':'Data Scientist','transformedPostingTitle':'role','locations':[{'countryID':'iso-country-USA'}]}
        def fetch(url, domains):
            return html({'search':{'page':2 if 'page=2' in url else 1,'totalRecords':2,'searchResults':[row]}}), url
        with patch('src.verification.fetch',side_effect=fetch):
            _, notes, coverage = collect(company, config)
        self.assertFalse(coverage['complete'])
        self.assertIn('repeated',notes[1])


class GeographyTests(unittest.TestCase):
    def test_us_foreign_mixed_and_ambiguous(self):
        cases = {'India - Hyderabad':'non_us','Canada, Remote':'non_us','Poland, Remote':'non_us','Ludwigshafen, RP, de':'non_us','Campoverde, Lazio, it':'non_us','England - Cambridge':'non_us','US, CA, Remote':'us','Mountain View, CA, USA; London, UK':'us','Spring House / Madrid / Raritan':'us','Remote':'unknown','Various locations':'unknown','Apple appears to have U.S. locations; verify':'unknown','Cambridge':'unknown','Cambridge, MA':'us'}
        for location, expected in cases.items():
            with self.subTest(location=location):
                self.assertEqual(country_scope({'location':location}),expected)
        self.assertEqual(country_scope({'location':'US','countries':['GBR']}),'non_us')
        self.assertEqual(country_scope({'countries':['GBR','USA']}),'us')
