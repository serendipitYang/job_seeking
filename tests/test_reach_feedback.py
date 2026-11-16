import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from src import reach_feedback as feedback


class ReachFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.job = {'id': 'one', 'company': 'Example', 'title': 'Scientist', 'description': 'Requires experience', 'match': {'score': 8}}

    def test_toggle_history_snapshots_and_idempotency(self):
        first = feedback.mark(self.base, self.job, True)
        feedback.mark(self.base, self.job, True)
        self.job['description'] = 'Updated requirements'
        feedback.mark(self.base, self.job, False)
        records = feedback.read_records(self.base)
        self.assertFalse(records['one']['over_my_reach'])
        self.assertEqual(records['one']['reach_first_marked_at'], first['reach_first_marked_at'])
        record = json.loads(feedback.path_for(self.base).read_text())['jobs']['one']
        self.assertEqual(len(record['history']), 2)
        self.assertEqual(record['history'][0]['job']['description'], 'Requires experience')
        self.assertEqual(record['history'][1]['job']['description'], 'Updated requirements')
        self.assertFalse((self.base/'applications.xlsx').exists())

    def test_failed_save_and_corrupt_file_preserved(self):
        feedback.mark(self.base, self.job, True)
        original = feedback.path_for(self.base).read_bytes()
        with patch('src.reach_feedback.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                feedback.mark(self.base, self.job, False)
        self.assertEqual(feedback.path_for(self.base).read_bytes(), original)
        feedback.path_for(self.base).write_text('broken')
        with self.assertRaises(ValueError):
            feedback.mark(self.base, self.job, False)
        self.assertEqual(feedback.path_for(self.base).read_text(), 'broken')
        with self.assertRaises(ValueError):
            feedback.mark(self.base, self.job, 'true')

    def test_concurrent_jobs_are_both_preserved(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda ident: feedback.mark(self.base, {**self.job,'id':ident},True), ['a','b']))
        self.assertEqual(set(feedback.read_records(self.base)), {'a','b'})
