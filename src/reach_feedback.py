"""Durable personal reach feedback, independent of application and nightly data."""
import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone


def path_for(base):
    return base / 'over_my_reach.json'


def load(base):
    path = path_for(base)
    if not path.exists():
        return {'version': 1, 'jobs': {}}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('jobs'), dict):
        raise ValueError('Invalid reach feedback file; existing data was preserved')
    for record in data['jobs'].values():
        if not isinstance(record, dict) or type(record.get('over_my_reach')) is not bool or not isinstance(record.get('history'), list):
            raise ValueError('Invalid reach feedback record; existing data was preserved')
    return data


def summary(record):
    return {k: record.get(k) for k in ('over_my_reach', 'reach_first_marked_at', 'reach_updated_at')}


def read_records(base):
    return {ident: summary(record) for ident, record in load(base)['jobs'].items()}


def mark(base, job, value):
    if type(value) is not bool:
        raise ValueError('over_my_reach must be a boolean')
    path = path_for(base)
    with path.with_suffix('.json.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load(base)
        previous = data['jobs'].get(job['id'])
        if previous and previous['over_my_reach'] == value:
            return summary(previous)
        stamp = datetime.now(timezone.utc).isoformat()
        snapshot = {k: job.get(k) for k in ('id', 'company', 'title', 'url', 'location', 'description', 'match', 'deadline', 'availability', 'source', 'discovery_queries')}
        record = {
            'over_my_reach': value,
            'reach_first_marked_at': (previous or {}).get('reach_first_marked_at') or (stamp if value else None),
            'reach_updated_at': stamp,
            'history': (previous or {}).get('history', []) + [{'at': stamp, 'over_my_reach': value, 'job': snapshot}],
        }
        data['jobs'][job['id']] = record
        fd, temporary = tempfile.mkstemp(prefix='.reach-', suffix='.tmp', dir=str(base))
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return summary(record)
