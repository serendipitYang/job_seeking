"""Public employer search endpoints; bounded pagination, exact-ID verification."""
import json
import math
import re
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlencode, parse_qs

QUERIES = ['Data Scientist', 'Applied Scientist', 'Research Scientist', 'Machine Learning', 'PhD', 'New Graduate', 'NLP', 'LLM', 'AI']
ROOTS = {'amazon': 'https://www.amazon.jobs', 'microsoft': 'https://apply.careers.microsoft.com'}


def identity(url):
    u = urlsplit(url)
    if u.hostname in ('amazon.jobs', 'www.amazon.jobs'):
        m = re.match(r'/[\w-]+/jobs/(\d+)(?:/|$)', u.path)
        return m[1] if m else None
    if u.hostname == 'apply.careers.microsoft.com':
        m = re.match(r'/careers/job/(\d+)(?:/|$)', u.path)
        return m[1] if m else parse_qs(u.query).get('pid', [None])[0]
    return None


def read_json(url, domains):
    from src.verification import fetch
    for attempt in range(3):
        try:
            raw, _ = fetch(url, domains, max_bytes=8_000_000)
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == 2:
                raise
            delay = exc.headers.get('Retry-After', '')
            if delay.isdigit() and int(delay) > 30:
                raise  # Defer to next run rather than retry before the employer permits it.
            time.sleep(int(delay) if delay.isdigit() else 2 ** (attempt + 1))


def normalize(row, kind, company):
    from src.fulltime import job, clean
    root = ROOTS[kind]
    if kind == 'amazon':
        ident = str(row['id_icims'])
        locations = [json.loads(v) if isinstance(v, str) else v for v in row.get('locations', [])]
        names = [v.get('location', '') for v in locations]
        countries = [v.get('countryIso3a') or v.get('normalizedCountryCode') for v in locations]
        description = '\n'.join(k.replace('_', ' ').title()+': '+clean(row.get(k,'')) for k in ('description','basic_qualifications','preferred_qualifications'))
        item = job(company, row['title'], '; '.join(filter(None, names)) or row.get('location',''), root+row['job_path'], description, 'amazon_catalog', ident)
        item.update(countries=list(filter(None,countries)) or [row.get('country_code','')], employment_type=row.get('job_schedule_type','unknown'), employer=row.get('company_name'))
    else:
        ident = str(row['id'])
        item = job(company,row['name'],'; '.join(row['locations']),root+row['positionUrl'],row.get('jobDescription',''),'microsoft_catalog',ident)
        # Country is the first component of Microsoft's explicit display locations.
        item.update(countries=list({v.split(',')[0].strip() for v in row['locations']}), employment_type=(row.get('efcustomTextEmploymentType') or ['unknown'])[0])
    if not ident.isdigit() or identity(item['url']) != ident:
        raise ValueError('Search result URL and ID disagree')
    return item


def fulltime(item):
    from src.meta import fulltime_title
    return fulltime_title(item['title']) and item.get('employment_type','unknown').lower() in ('full-time','full_time','unknown')


def collect(company, config):
    from src.fulltime import relevant
    from src.geography import country_scope
    kind = company['type']; root = ROOTS[kind]
    queries = company.get('queries', QUERIES)
    cap = config.get('collection',{}).get(kind+'_max_pages_per_query',250)
    def search(query):
        unique = {}; offset = 0; pages = 0; total = None; size = 100 if kind == 'amazon' else 10; notes = []
        for _ in range(cap):
            params = {'base_query':query,'offset':offset,'result_limit':100} if kind == 'amazon' else {'domain':'microsoft.com','query':query,'start':offset}
            url = root+('/en/search.json?' if kind == 'amazon' else '/api/pcsx/search?')+urlencode(params)
            try:
                if kind == 'microsoft': time.sleep(.5)
                data = read_json(url,company['domains'])
                if kind == 'amazon':
                    if data.get('error'): raise ValueError('Amazon search error')
                    rows, count = data['jobs'], data['hits']
                else:
                    if data.get('status') != 200: raise ValueError('Microsoft search error')
                    rows, count = data['data']['positions'], data['data']['count']
                if type(count) is not int or not isinstance(rows,list): raise ValueError('Search schema changed')
                if total is not None and count != total: notes.append('Result count changed during traversal')
                total = count
                if rows: size = len(rows) if pages == 0 else size
                pages += 1; before = len(unique)
                for row in rows:
                    item = normalize(row,kind,company['name']); unique[item['id']] = item
                offset += len(rows)
                if len(unique) >= total: break
                if len(unique) == before: notes.append('Empty or repeated page before reported total'); break
            except Exception as exc:
                notes.append(f'{type(exc).__name__}: {exc}'); break
        complete = total is not None and len(unique) == total and not notes
        if not complete and not notes: notes.append('Pagination cap reached')
        coverage = dict(query=query,complete=complete,pages_checked=pages,pages_total=math.ceil(total/size) if total is not None else None,listings_seen=len(unique),reported_total=total)
        print(f'{company["name"]} {query}: {len(unique)}/{total} listings ({"complete" if complete else "partial"}) {notes}',flush=True)
        return unique, coverage, [query+': '+n for n in notes]
    all_items = {}; coverage = []; notes = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        for items, cov, errors in pool.map(search,queries):
            coverage.append(cov); notes.extend(errors)
            for ident, item in items.items():
                if ident not in all_items: all_items[ident] = item; item['discovery_queries'] = []
                all_items[ident]['discovery_queries'].append(cov['query'])
    keywords = config['keywords']+['research','scientist','AI engineer','AI/ML','AI research','AI software','data engineer']
    found = [j for j in all_items.values() if fulltime(j) and country_scope(j) != 'non_us' and
             (relevant(j['title'],keywords) or (re.search(r'engineer',j['title'],re.I) and any(q in j['discovery_queries'] for q in ('PhD','New Graduate'))))]
    cov = dict(complete=all(c['complete'] for c in coverage), queries=coverage,unique_listings=len(all_items),relevant_jobs=len(found),scope='Public keyword search, all returned pages; overlapping queries deduplicated; US/full-time title filters; individual details verified separately')
    for key in ('pages_checked','pages_total','listings_seen','reported_total'): cov[key] = sum(c[key] or 0 for c in coverage)
    return found, notes, cov


class AmazonPage(HTMLParser):
    def __init__(self):
        super().__init__(); self.canonical = None; self.apply = []; self.title = []; self.depth = 0
    def handle_starttag(self,tag,attrs):
        a = dict(attrs)
        if tag == 'meta' and a.get('property') == 'og:url': self.canonical = a.get('content')
        if tag == 'a' and '/apply' in a.get('href',''): self.apply.append(a['href'])
        if tag == 'h1': self.depth += 1
    def handle_endtag(self,tag):
        if tag == 'h1': self.depth = max(0,self.depth-1)
    def handle_data(self,data):
        if self.depth: self.title.append(data)


def details(url, domains):
    from src.verification import fetch, Page
    from src.fulltime import clean
    ident = identity(url)
    if not ident: raise ValueError('Not an individual employer job URL')
    if urlsplit(url).hostname == 'apply.careers.microsoft.com':
        api = ROOTS['microsoft']+'/api/pcsx/position_details?'+urlencode({'position_id':ident,'domain':'microsoft.com','hl':'en'})
        data = read_json(api, domains)
        row = data.get('data',{})
        if data.get('status') != 200 or str(row.get('id')) != ident or len(row.get('jobDescription','')) < 200:
            raise ValueError('Microsoft did not return the requested full job description')
        item = normalize(row,'microsoft','Microsoft')
        return {k:v for k,v in item.items() if k in ('title','url','description','location','countries','employment_type')}
    raw, checked = fetch(url,domains)
    p = AmazonPage(); p.feed(raw)
    page = Page(); page.feed(raw); visible = clean(' '.join(page.text))
    if identity(checked) != ident or identity(p.canonical or '') != ident or not any(re.search(r'/jobs/'+ident+r'/apply(?:[?#]|$)',v) for v in p.apply):
        raise ValueError('Amazon canonical ID or exact job application link unavailable')
    # Require the exact live page and extract its current qualifications.
    if not p.title or not re.search('BASIC QUALIFICATIONS',visible,re.I) or len(visible)<400:
        raise ValueError('Amazon job title/qualifications unavailable')
    sections = re.findall(r'<h2[^>]*>(Description|Basic Qualifications|Preferred Qualifications)</h2>(.*?)</div>', raw, re.I|re.S)
    if len(sections) != 3: raise ValueError('Amazon description sections changed')
    return {'title':clean(' '.join(p.title)), 'url':p.canonical, 'description':'\n'.join(name+': '+clean(body) for name,body in sections)}


def seniority_priority(item):
    """Queue hint only: never infer eligibility or discard a job from its title."""
    title = item['title']
    if re.search(r'\b(principal|staff|director|head|manager|distinguished|lead)\b', title,re.I): return 2
    if re.search(r'\b(senior|sr\.?|III)\b',title,re.I): return 1
    return 0
