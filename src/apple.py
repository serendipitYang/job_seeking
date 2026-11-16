"""Apple's public server-rendered router data, parsed as JSON (never executed)."""
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit, quote


def hydration(raw):
    match = re.search(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\(("(?:\\.|[^"\\])*")\)', raw)
    if not match:
        raise ValueError('Apple structured page data is unavailable')
    data = json.loads(json.loads(match[1]))
    if data.get('errors'):
        raise ValueError('Apple page returned router errors')
    return data['loaderData']


def identity(url):
    u = urlsplit(url)
    match = re.search(r'/details/(\d+(?:-\d+)?)', u.path)
    return match[1] if u.hostname == 'jobs.apple.com' and match else None


def location_text(locations):
    return '; '.join(', '.join(dict.fromkeys(str(l[k]) for k in ('city', 'name', 'stateProvince', 'countryName') if l.get(k))) for l in locations)


def details(raw, url):
    from src.fulltime import clean
    info = hydration(raw).get('jobDetails', {}).get('jobsData', {})
    number = str(info.get('jobNumber', ''))
    expected = identity(url)
    if not expected or (number != expected and not ('-' not in expected and number.split('-')[0] == expected)):
        raise ValueError('Apple job identity does not match the requested posting')
    if not info.get('postingTitle') or not info.get('description'):
        raise ValueError('Apple did not supply the full job description')
    fields = ('jobSummary', 'description', 'minimumQualifications', 'preferredQualifications', 'educationAndExperience', 'additionalRequirements')
    return dict(title=info['postingTitle'], description='\n\n'.join(k + ': ' + clean(info[k]) for k in fields if info.get(k)),
                location=location_text(info.get('locations', [])),
                countries=[l.get('countryID', '').replace('iso-country-', '') for l in info.get('locations', [])],
                posted_date=info.get('postingDateMeta'),
                url=f'https://jobs.apple.com/en-us/details/{number}/{quote(info.get("transformedPostingTitle", ""))}')


def collect(company, config):
    from src.verification import fetch
    from src.fulltime import job, relevant
    max_pages = config['collection'].get('apple_max_pages', 300)
    def page(number, alternate=False):
        url = 'https://jobs.apple.com/en-us/search?location=united-states-USA' + (f'&page={number}' if number > 1 else '')
        if alternate and number > 1:
            url = f'https://jobs.apple.com/en-us/search?page={number}&location=united-states-USA'
        raw, _ = fetch(url, company['domains'])
        data = hydration(raw)['search']
        if int(data['page']) != number or not isinstance(data.get('searchResults'), list):
            raise ValueError('Apple pagination response does not match requested page')
        return data
    first = page(1)
    total = int(first['totalRecords'])
    page_size = len(first['searchResults'])
    if not total or not page_size:
        raise ValueError('Apple returned an unexpectedly empty US catalog; completeness cannot be established')
    pages = math.ceil(total / (page_size or 20))
    rows, seen_pages, failures = list(first['searchResults']), {tuple(r['id'] for r in first['searchResults'])}, []
    completed = 1
    def safe_page(n):
        error = None
        for attempt in range(2):
            try:
                data = page(n, alternate=attempt > 0)
                if not data['searchResults']:
                    raise ValueError('Unexpected empty catalog page')
                return n, data, None
            except Exception as exc:
                error = str(exc)
                if attempt == 0:
                    time.sleep(1)
        return n, None, error
    with ThreadPoolExecutor(max_workers=4) as pool:
        for n, data, error in pool.map(safe_page, range(2, min(pages, max_pages) + 1)):
            if error:
                failures.append(f'Page {n}: {error}')
                continue
            signature = tuple(r['id'] for r in data['searchResults'])
            if not signature or signature in seen_pages:
                failures.append(f'Page {n}: empty or repeated page')
                continue
            seen_pages.add(signature)
            rows.extend(data['searchResults'])
            completed += 1
            if n % 25 == 0:
                print(f'Apple catalog: {n}/{pages} pages', flush=True)
    unique = {r['id']: r for r in rows}
    found = []
    for row in unique.values():
        locations = row.get('locations', [])
        if not any(l.get('countryID') == 'iso-country-USA' for l in locations):
            continue
        if not relevant(row['postingTitle'], config['keywords']):
            continue
        number = row['id']
        url = f'https://jobs.apple.com/en-us/details/{number}/{quote(row["transformedPostingTitle"])}'
        item = job(company['name'], row['postingTitle'], location_text(locations), url, row.get('jobSummary', ''), 'apple_catalog', number)
        item['countries'] = [l.get('countryID', '').replace('iso-country-', '') for l in locations]
        found.append(item)
    seed_notes = []
    for url in company.get('seed_urls', []):
        if identity(url) in {identity(item['url']) for item in found}:
            continue
        try:
            raw, _ = fetch(url, company['domains'])
            info = details(raw, url)
            item = job(company['name'], info['title'], info['location'], info['url'], info['description'], 'apple_seed', identity(info['url']))
            item.update(info)
            found.append(item)
        except Exception as exc:
            seed_notes.append(f'Seed {url}: {exc}')
    complete = not failures and pages <= max_pages and len(unique) >= total
    coverage = dict(complete=complete, pages_checked=completed, pages_total=pages, listings_seen=len(unique), reported_total=total,
                    relevant_jobs=len(found), scope='Apple US catalog; configured title keywords; internships excluded')
    notes = [] if complete else [f'Catalog incomplete: {completed}/{pages} pages, {len(unique)}/{total} unique listings'] + failures[:5]
    return found, notes + seed_notes, coverage
