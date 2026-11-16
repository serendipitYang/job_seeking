"""Logged-out Meta Careers catalog and exact posting verification.

Only public read-only search operations are used. No account cookies are loaded.
"""
import http.cookiejar
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

ROOT = 'https://www.metacareers.com'
OPERATIONS = ('CareersJobSearchResultsV2DataQuery', 'CareersJobSearchHideFiltersBarV2Query')


def identity(url):
    u = urllib.parse.urlsplit(url)
    match = re.fullmatch(r'/(?:profile/job_details|jobs)/(\d+)/?', u.path)
    return match[1] if u.hostname in ('www.metacareers.com', 'metacareers.com') and match else None


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.canonical = [], None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'script' and attrs.get('src', '').startswith('https://static.xx.fbcdn.net/'):
            self.scripts.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical = attrs.get('href')


def operation_ids(raw):
    ids = {}
    for name in OPERATIONS:
        match = re.search(r'__d\("' + name + r'_candidate_portalRelayOperation".{0,250}?exports="(\d+)"', raw)
        if match:
            ids[name] = match[1]
    return ids


class PublicSearch:
    def __init__(self):
        from src.verification import SafeRedirect, fetch
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), SafeRedirect(['metacareers.com']))
        req = urllib.request.Request(ROOT + '/jobsearch/', headers={'User-Agent':'Mozilla/5.0'})
        with self.opener.open(req, timeout=30) as response:
            raw = response.read(2_000_001).decode('utf-8')
        if len(raw) > 2_000_000:
            raise ValueError('Meta bootstrap exceeds size limit')
        token = re.search(r'\["LSD",\[\],\{"token":"([^"]+)"', raw)
        if not token:
            raise ValueError('Meta public search bootstrap unavailable')
        self.token = token[1]
        links = Links(); links.feed(raw)
        self.ids = {}
        # Discover changing public operation IDs from the site's own current bundles.
        for url in list(dict.fromkeys(links.scripts))[:12]:
            script, _ = fetch(url, ['static.xx.fbcdn.net'], max_bytes=8_000_000)
            self.ids.update(operation_ids(script))
            if all(name in self.ids for name in OPERATIONS):
                break
        if not all(name in self.ids for name in OPERATIONS):
            raise ValueError('Meta search operations changed or were unavailable')

    def query(self, name):
        if name not in OPERATIONS:
            raise ValueError('Only public job-search reads are supported')
        variables = {'search_input': {'q': None, 'results_per_page': None}}
        if name == OPERATIONS[0]:
            variables.update(isLoggedIn=False, viewasUserID=None)
        payload = {'doc_id':self.ids[name], 'variables':json.dumps(variables), 'lsd':self.token,
                   'fb_api_req_friendly_name':name, 'fb_api_caller_class':'RelayModern',
                   '__a':'1', '__user':'0', '__comet_req':'1', 'server_timestamps':'true'}
        req = urllib.request.Request(ROOT+'/api/graphql/', data=urllib.parse.urlencode(payload).encode(), headers={
            'Content-Type':'application/x-www-form-urlencoded', 'User-Agent':'Mozilla/5.0',
            'Referer':ROOT+'/jobsearch/', 'Origin':ROOT, 'X-FB-LSD':self.token})
        with self.opener.open(req, timeout=45) as response:
            raw = response.read(8_000_001).decode('utf-8')
        if len(raw) > 8_000_000:
            raise ValueError('Meta search response exceeds size limit')
        data = json.loads(raw.removeprefix('for (;;);'))
        if data.get('errors'):
            raise ValueError('Meta public search returned GraphQL errors')
        result = data.get('data', {}).get('job_search_with_featured_jobs_v2')
        if not isinstance(result, dict):
            raise ValueError('Meta search response schema changed')
        return result


def fulltime_title(title):
    return not re.search(r'\b(intern(?:ship)?|co[ -]?op|contract(?:or)?|temporary|part.time|student researcher|apprentice(?:ship)?|STE)\b', title, re.I)


def details(raw, url):
    from src.verification import Page, postings
    from src.fulltime import clean
    links = Links(); links.feed(raw)
    if not identity(url) or identity(links.canonical or '') != identity(url):
        raise ValueError('Meta canonical posting ID did not match the requested job')
    page = Page(); page.feed(raw)
    rows = [row for ld in page.ld for row in postings(ld)]
    if len(rows) != 1:
        raise ValueError('Meta did not return one individual JobPosting')
    row = rows[0]
    if not row.get('title') or not row.get('description') or not row.get('qualifications'):
        raise ValueError('Meta posting is missing its description or qualifications')
    if row.get('hiringOrganization', {}).get('name') != 'Meta':
        raise ValueError('Unexpected employer in Meta job data')
    locations = row.get('jobLocation', [])
    if isinstance(locations, dict): locations = [locations]
    countries, names = [], []
    for loc in locations:
        address = loc.get('address', {})
        country = address.get('addressCountry', '')
        if isinstance(country, dict): country = country.get('name', '')
        if country: countries.append(country)
        names.append(', '.join(v for v in (loc.get('name') or address.get('addressLocality'), country) if v))
    return dict(title=row['title'], url=ROOT+'/profile/job_details/'+identity(url)+'/',
                description='\n\n'.join(key+': '+clean(row[key]) for key in ('description','responsibilities','qualifications','skills') if row.get(key)),
                location='; '.join(names), countries=list(dict.fromkeys(countries)),
                employment_type=row.get('employmentType', 'unknown'), posted_date=row.get('datePosted'),
                employer='Meta', deadline_raw=row.get('validThrough'))


def collect(company, config):
    from src.fulltime import job, relevant
    from src.geography import country_scope
    api = PublicSearch()
    result = api.query(OPERATIONS[0])
    count = api.query(OPERATIONS[1]).get('job_count')
    rows = result.get('all_jobs')
    if not isinstance(rows, list) or type(count) is not int or count <= 0:
        raise ValueError('Meta catalog count or rows unavailable')
    unique = {}
    for row in rows:
        if not isinstance(row, dict) or not str(row.get('id','')).isdigit() or not row.get('title') or not isinstance(row.get('locations'),list):
            raise ValueError('Meta catalog job schema changed')
        unique[row['id']] = row
    found = []
    keywords = company.get('keywords', ['data scien','research','scientist','machine learning','artificial intelligence','PhD','AI engineer','AI research','data engineer','analytics'])
    for ident, row in unique.items():
        if not fulltime_title(row['title']) or not relevant(row['title'], keywords):
            continue
        item = job(company['name'],row['title'],'; '.join(row['locations']),ROOT+'/profile/job_details/'+ident+'/', '', 'meta_catalog', ident)
        if country_scope(item) == 'non_us':
            continue
        item['discovery_queries'] = [k for k in keywords if k.lower() in row['title'].lower()]
        item['teams'] = row.get('teams', [])
        found.append(item)
    complete = len(unique) == count
    coverage = dict(complete=complete,pages_checked=1,pages_total=1,listings_seen=len(unique),reported_total=count,
                    unique_listings=len(unique),relevant_jobs=len(found),
                    scope='Meta public global catalog (returned in one response; site paginates locally); title keywords, US and full-time filters; details verified separately')
    print(f'Meta catalog: {len(unique)}/{count} jobs; {len(found)} relevant candidates', flush=True)
    notes = [] if complete else [f'Meta catalog returned {len(unique)} unique jobs versus {count} reported; coverage is partial']
    return found, notes, coverage
