"""Conservative, free employer-page verification; uncertainty never means closed."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def allowed_url(url, domains):
    u = urllib.parse.urlsplit(url)
    return (u.scheme == 'https' and not u.username and not u.password and u.port in (None, 443)
            and any(u.hostname == d or (u.hostname or '').endswith('.' + d) for d in domains))


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, domains):
        self.domains = domains

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl, self.domains):
            raise ValueError('Redirect leaves configured employer domains')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, domains, max_bytes=2_000_000):
    if not allowed_url(url, domains):
        raise ValueError('URL is outside configured HTTPS employer domains')
    opener = urllib.request.build_opener(SafeRedirect(domains))
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 JobResearch/1.0', 'Accept': 'text/html,application/json'})
    with opener.open(req, timeout=15) as response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError('Page exceeds verification size limit')
        return body.decode('utf-8', errors='replace'), response.geturl()


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text, self.ld, self.buffer = [], [], []
        self.hidden, self.json_script = 0, False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
            self.json_script = True
            self.buffer = []

    def handle_endtag(self, tag):
        if tag == 'script' and self.json_script:
            try:
                self.ld.append(json.loads(''.join(self.buffer)))
            except ValueError:
                pass
            self.json_script = False
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if self.json_script:
            self.buffer.append(data)
        elif not self.hidden:
            self.text.append(data)


def postings(value):
    if isinstance(value, list):
        for item in value:
            yield from postings(item)
    elif isinstance(value, dict):
        kinds = value.get('@type', [])
        if 'JobPosting' in ([kinds] if isinstance(kinds, str) else kinds):
            yield value
        if '@graph' in value:
            yield from postings(value['@graph'])


def deadline(value, source):
    """Only normalize unambiguous dates; preserve exact source value as evidence."""
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        parsed = None
        for fmt in ('%B %d, %Y', '%b %d, %Y', '%m/%d/%Y'):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    return {'date': parsed.date().isoformat(), 'raw': text, 'source': source}


def text_deadline(text):
    match = re.search(r'(?:application deadline|apply by|closing date|anticipated to close on)\s*[:\-]?\s*'
                      r'(\d{4}-\d{2}-\d{2}|[A-Za-z]+ \d{1,2}, \d{4}|\d{1,2}/\d{1,2}/\d{4})', text, re.I)
    return deadline(match[1], 'Employer text: ' + match[0]) if match else None


def matching_title(a, b):
    words = lambda s: set(re.findall(r'[a-z0-9]+', s.lower()))
    x, y = words(a), words(b)
    return bool(x) and len(x & y) / max(len(x), len(y)) >= .7


def verify_job(item, company):
    result = {'status': 'unverified', 'checked_at': timestamp(), 'reason': '', 'checked_url': item['url']}
    due = None
    domains = company.get('domains', [])
    try:
        url = item['url']
        u = urllib.parse.urlsplit(url)
        workday = re.fullmatch(r'([\w-]+)\.wd\d+\.myworkdayjobs\.com', u.hostname or '')
        if u.hostname == 'jobs.apple.com':
            from src.apple import details
            raw, checked = fetch(url, domains)
            info = details(raw, url)
            result.update(status='open', reason='Apple structured job ID and full description verified', checked_url=checked)
            return {'availability': result, 'deadline': text_deadline(info['description']), **info}
        elif u.hostname in ('www.google.com', 'google.com', 'careers.google.com'):
            from src.google import details, JobNotFound
            raw, checked = fetch(url, domains)
            result['checked_url'] = checked
            try:
                info = details(raw, checked)
            except JobNotFound as exc:
                result.update(status='closed', reason=str(exc))
                return {'availability': result, 'deadline': None}
            result.update(status='open', reason='Google selected job ID, qualifications and application link verified')
            return {'availability': result, 'deadline': text_deadline(info['description']), **info}
        elif u.hostname in ('www.metacareers.com', 'metacareers.com'):
            from src.meta import details
            raw, checked = fetch(url, domains)
            info = details(raw, checked)
            due = deadline(info.pop('deadline_raw', None), 'Meta JobPosting.validThrough') or text_deadline(info['description'])
            result.update(status='open', reason='Meta canonical job ID, description and qualifications verified', checked_url=checked)
            if due and due['date'] < datetime.now(timezone.utc).date().isoformat():
                result.update(status='closed', reason='Meta structured application deadline has passed')
            return {'availability': result, 'deadline': due, **info}
        elif u.hostname in ('amazon.jobs', 'www.amazon.jobs', 'apply.careers.microsoft.com'):
            from src.amazon_microsoft import details
            info = details(url, domains)
            result.update(status='open', reason='Exact employer posting ID and full qualifications verified')
            return {'availability': result, 'deadline': text_deadline(info.get('description', item.get('description',''))), **info}
        elif workday and '/job/' in u.path:
            prefix, path = u.path.split('/job/', 1)
            site = prefix.strip('/').split('/')[-1]
            api = f'https://{u.hostname}/wday/cxs/{workday[1]}/{site}/job/{path}'
            raw, checked = fetch(api, domains)
            info = json.loads(raw).get('jobPostingInfo', {})
            result['checked_url'] = checked
            if not info.get('jobDescription') or not matching_title(item['title'], info.get('title', '')):
                result['reason'] = 'Employer API did not return this job description/title'
            else:
                result.update(status='open', reason='Individual employer job detail is available')
                due = deadline(info.get('endDate') or info.get('applicationDeadline'), 'Employer job API')
                if not due:
                    page = Page(); page.feed(info['jobDescription']); due = text_deadline(' '.join(page.text))
        else:
            raw, checked = fetch(url, domains)
            result['checked_url'] = checked
            page = Page(); page.feed(raw)
            text = re.sub(r'\s+', ' ', ' '.join(page.text)).strip()
            closed = re.search(r'(?:this (?:job|position|requisition) (?:is no longer available|has been (?:filled|closed))|'
                               r'this job is no longer accepting applications|job (?:has expired|not found)|'
                               r'the job you (?:are looking for|requested) (?:is no longer available|cannot be found))', text, re.I)
            matching = [p for ld in page.ld for p in postings(ld) if matching_title(item['title'], p.get('title', ''))]
            if closed:
                result.update(status='closed', reason=closed[0])
            elif len(matching) == 1 and matching[0].get('description'):
                result.update(status='open', reason='Matching employer JobPosting data found')
                due = deadline(matching[0].get('validThrough'), 'Employer JobPosting.validThrough')
                if due and due['date'] < datetime.now(timezone.utc).date().isoformat():
                    result.update(status='closed', reason='Employer structured application deadline has passed')
            elif item['title'].lower() in text.lower() and len(text) > 400 and re.search(r'\bapply\b', text, re.I) and '/job' in urllib.parse.urlsplit(checked).path.lower():
                result.update(status='open', reason='Job title and application link text found on individual page')
            else:
                result['reason'] = 'Could not confirm individual posting (redirect, JS page, or access challenge)'
            due = due or (text_deadline(text) if result['status'] == 'open' else None)
    except urllib.error.HTTPError as exc:
        result.update(status='closed' if exc.code in (404, 410) else 'unverified', reason=f'Employer returned HTTP {exc.code}')
    except Exception as exc:
        result['reason'] = f'Check inconclusive: {type(exc).__name__}: {exc}'
    return {'availability': result, 'deadline': due}


def verify_jobs(items, companies):
    lookup = {c['name']: c for c in companies}
    def check(item):
        item.update(verify_job(item, lookup.get(item['company'], {})))
    with ThreadPoolExecutor(max_workers=4) as pool:
        for count, _ in enumerate(pool.map(check, items), 1):
            if count % 50 == 0:
                print(f'Verified {count}/{len(items)} links', flush=True)
