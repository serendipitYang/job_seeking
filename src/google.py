"""Google Careers public structured pages; parse JSON without executing JavaScript."""
import html
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode, urlsplit

ROOT = 'https://www.google.com/about/careers/applications/'
DEFAULT_QUERIES = ['PhD New grad', 'AI', 'Data', 'Research Data Scientist', 'PhD', 'New grad']


class JobNotFound(ValueError):
    pass


def identity(url):
    u = urlsplit(url)
    match = re.search(r'/jobs/results/(\d+)', u.path)
    return match[1] if u.hostname in ('google.com', 'www.google.com', 'careers.google.com') and match else None


def blocks(raw):
    result = {}
    for match in re.finditer(r"AF_initDataCallback\(\{key: '([^']+)', hash: '[^']+', data:", raw):
        result[match[1]], _ = json.JSONDecoder().raw_decode(raw[match.end():])
    if not result:
        raise ValueError('Google structured job data unavailable')
    return result


def links(raw):
    result = {}
    for path in re.findall(r'href="([^"]*jobs/results/\d+[^"?]*)', raw):
        path = html.unescape(path)
        url = path if path.startswith('https://') else ROOT + path.lstrip('/')
        ident = identity(url)
        if ident:
            result[ident] = url
    return result


def is_row(row):
    return isinstance(row, list) and len(row) >= 20 and isinstance(row[0], str) and row[0].isdigit() and isinstance(row[1], str)


def normalize(row, url):
    from src.fulltime import clean
    if not is_row(row) or identity(url) != row[0]:
        raise ValueError('Google posting ID or schema mismatch')
    def content(index):
        value = row[index]
        return clean(value[1]) if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str) else ''
    if not content(4) or not content(10) or not isinstance(row[2], str) or not row[2].startswith(ROOT + 'signin?'):
        raise ValueError('Google posting lacks qualifications, description, or application link')
    locations = row[9] or []
    if not isinstance(locations, list) or not all(isinstance(l, list) and len(l) >= 6 for l in locations):
        raise ValueError('Google location schema changed')
    return dict(title=row[1], url=url, description='\n\n'.join(s for s in [content(4), content(10), content(3), content(15), content(18)] if s),
                location='; '.join(l[0] for l in locations), countries=list(dict.fromkeys(l[5] for l in locations if l[5])),
                employer=row[7])


def details(raw, url):
    data = blocks(raw)
    # ds:1 is the surrounding SEARCH RESULTS, never evidence of the selected job.
    selected = data.get('ds:0')
    if isinstance(selected, list) and len(selected) == 1 and is_row(selected[0]):
        return normalize(selected[0], url)
    from src.verification import Page
    page = Page(); page.feed(raw)
    if re.search(r'Job not found\.?\s*This job may have been taken down', ' '.join(page.text), re.I):
        raise JobNotFound('Google states the requested job was not found')
    raise ValueError('Google did not return the requested individual posting')


def search_page(raw, page_number):
    data = blocks(raw).get('ds:1')
    if not isinstance(data, list) or len(data) < 4 or not isinstance(data[2], int):
        raise ValueError('Google search schema changed')
    rows, total, size = data[0] or [], data[2], data[3]
    if not isinstance(rows, list) or not all(is_row(r) for r in rows) or not isinstance(size, int) or size <= 0:
        raise ValueError('Google search rows or page size invalid')
    if total and not rows:
        raise ValueError('Unexpected empty Google search page')
    if rows:
        shown = re.search(r'Showing (\d+) to (\d+) of ([\d,]+) rows', raw)
        if not shown or int(shown[1]) != (page_number - 1) * size + 1:
            raise ValueError('Google returned an unexpected page number')
    return rows, total, size, links(raw)


def fulltime_title(title):
    return not re.search(r'\b(intern(?:ship)?|co[ -]?op|temporary|contractor|part.time|student researcher|apprentice(?:ship)?)\b', title, re.I)


def candidate(title, queries, description=""):
    if not fulltime_title(title):
        return False
    if re.search(r'\b(data (?!cent(?:er|re))|research|scientist|machine learning|AI|artificial intelligence|PhD|graduate|university|analytics|statistic|computational|NLP|LLM)\b', title, re.I):
        return True
    if 'AI' in queries and re.search(r'\b(engineer|developer)\b', title, re.I) and re.search(r'machine learning|large language model|LLM|deep learning|artificial intelligence', description, re.I):
        return True
    return any('phd' in q.lower() or 'grad' in q.lower() for q in queries) and bool(re.search(r'\b(engineer|developer)\b', title, re.I))


def collect(company, config):
    from src.verification import fetch
    from src.fulltime import job
    queries = company.get('queries', DEFAULT_QUERIES)
    cap = config['collection'].get('google_max_pages_per_query', 100)
    all_rows, query_reports, notes = {}, [], []
    def get(query, n):
        error = None
        for attempt in range(2):
            params = [('location', 'United States'), ('q', query), ('page', n)]
            if attempt:
                params.reverse()
                time.sleep(.5)
            url = ROOT + 'jobs/results/?' + urlencode(params)
            try:
                raw, _ = fetch(url, company['domains'])
                return search_page(raw, n), None
            except Exception as exc:
                error = str(exc)
        return None, error
    for query in queries:
        print(f'Google query: {query}', flush=True)
        first, error = get(query, 1)
        if error:
            notes.append(f'{query}: {error}')
            query_reports.append(dict(query=query, complete=False, pages_checked=0, pages_total=None, listings_seen=0, reported_total=None))
            continue
        rows, total, size, urls = first
        pages = max(1, math.ceil(total / size))
        unique, checked, failed = {}, 0, []
        def consume(n, data, error):
            nonlocal checked
            if error:
                failed.append(f'page {n}: {error}'); return
            batch, _, _, mapping = data
            if batch and all(r[0] in unique for r in batch):
                failed.append(f'page {n}: repeated results'); return
            checked += 1
            for row in batch:
                ident = row[0]
                unique[ident] = row
                if ident not in mapping:
                    failed.append(f'page {n}: posting link absent for {ident}'); continue
                prior = all_rows.get(ident, {'queries': []})
                all_rows[ident] = {'row': row, 'url': mapping[ident], 'queries': list(dict.fromkeys(prior['queries'] + [query]))}
        consume(1, first, None)
        with ThreadPoolExecutor(max_workers=4) as pool:
            for n, (data, error) in zip(range(2, min(cap, pages)+1), pool.map(lambda n: get(query, n), range(2, min(cap, pages)+1))):
                consume(n, data, error)
        complete = not failed and pages <= cap and len(unique) >= total
        query_reports.append(dict(query=query, complete=complete, pages_checked=checked, pages_total=pages, listings_seen=len(unique), reported_total=total))
        if not complete:
            notes.append(f'{query}: {checked}/{pages} pages, {len(unique)}/{total} listings; ' + '; '.join(failed[:3]))
        print(f'Google {query}: {len(unique)}/{total} listings, {checked}/{pages} pages', flush=True)
    found = []
    for ident, record in all_rows.items():
        row = record['row']
        if not candidate(row[1], record['queries'], str(row[4]) + ' ' + str(row[10])):
            continue
        try:
            info = normalize(row, record['url'])
            if 'US' not in info['countries']:
                continue
            item = job(company['name'], info['title'], info['location'], info['url'], info['description'], 'google_catalog', ident)
            item.update(info, discovery_queries=record['queries'])
            found.append(item)
        except ValueError as exc:
            notes.append(f'{ident}: {exc}')
    coverage = dict(complete=all(q['complete'] for q in query_reports) and not notes,
                    pages_checked=sum(q['pages_checked'] for q in query_reports), pages_total=sum(q['pages_total'] or 1 for q in query_reports),
                    listings_seen=sum(q['listings_seen'] for q in query_reports), reported_total=sum(q['reported_total'] or 0 for q in query_reports),
                    unique_listings=len(all_rows), relevant_jobs=len(found), queries=query_reports,
                    scope='Google Careers US keyword searches; per-query totals overlap; deduplicated by job ID; internships excluded')
    return found, notes, coverage
