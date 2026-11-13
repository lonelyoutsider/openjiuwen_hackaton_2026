import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.llm import Client
from harness.profile import resolve_json_mode
from harness.provenance import fingerprint
from harness.tools import run_python
from scripts.release_set import build_fresh_set, build_release_set
from scripts.run_release_check import main


class ReleaseTests(unittest.TestCase):
    def test_provider_defaults_never_assume_final_proxy_support(self):
        self.assertTrue(resolve_json_mode('https://api.neuraldeep.ru/v1'))
        self.assertTrue(resolve_json_mode('https://api.neuraldeep.ru:443/v1'))
        for url in ('http://api.neuraldeep.ru/v1', 'https://api.neuraldeep.ru:444/v1',
                    'http://proxy:8000/v1', 'https://api.neuraldeep.ru.evil/v1'):
            self.assertFalse(resolve_json_mode(url))
        self.assertFalse(resolve_json_mode('https://api.neuraldeep.ru/v1', False))
        self.assertTrue(resolve_json_mode('http://proxy/v1', True))

    def test_output_allowance_shrinks_without_extra_requests(self):
        client = Client('https://api.neuraldeep.ru/v1', 'fake', 400)
        response = {'usage': {'prompt_tokens': 100, 'completion_tokens': 10},
                    'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}]}
        with patch.object(client.opener, 'open', return_value=io.BytesIO(json.dumps(response).encode())) as request:
            self.assertEqual(client.complete([], 1024), 'ok')
        body = json.loads(request.call_args.args[0].data)
        self.assertGreaterEqual(body['max_tokens'], 64)
        self.assertLess(body['max_tokens'], 1024)
        self.assertEqual(client.calls, 1)
        self.assertEqual(client.snapshot()['weighted_tokens'], 20)
        self.assertLessEqual(client.last_request_metadata['reservation_weighted_tokens'], 400)

    def test_larger_budget_preserves_output_cap(self):
        client = Client('https://api.neuraldeep.ru/v1', 'fake', 200000)
        response = {'usage': {'prompt_tokens': 1, 'completion_tokens': 1},
                    'choices': [{'message': {'content': 'ok'}}]}
        with patch.object(client.opener, 'open', return_value=io.BytesIO(json.dumps(response).encode())) as request:
            client.complete([], 1024)
        self.assertEqual(json.loads(request.call_args.args[0].data)['max_tokens'], 1024)

    def test_image_fingerprint_detects_changes_but_normalizes_windows_newlines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'harness').mkdir()
            for name in ('run_agent.py', 'requirements.lock', 'harness/a.py'):
                (root / name).write_bytes(b'one\ntwo\n')
            before = fingerprint(root)
            (root / 'run_agent.py').write_bytes(b'one\r\ntwo\r\n')
            self.assertEqual(fingerprint(root), before)
            (root / 'harness/a.py').write_bytes(b'changed\n')
            self.assertNotEqual(fingerprint(root), before)

    def test_release_composition_and_private_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            labels = build_release_set(root)
            self.assertEqual(len(labels), 21)
            self.assertEqual(sum(v['expected'] is not None for v in labels.values()), 19)
            self.assertEqual(sum(v['reward'] for v in labels.values() if v['expected'] is not None), 51)
            for name, label in labels.items():
                raw = json.loads((root / name / 'task.json').read_text())
                self.assertNotIn('private_check', raw)
                self.assertNotIn('validation_group', raw)
                self.assertNotIn('source_suite', raw)

    def test_fresh_coding_references_pass_independent_checks_and_bugs_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); labels = build_fresh_set(root)
            fixes = {
                'coding_median': ('metrics.py', 'def median(values):\n    xs = sorted(values)\n    if not xs: raise ValueError("empty")\n    n = len(xs)\n    return xs[n//2] if n%2 else (xs[n//2-1]+xs[n//2])/2\n'),
                'coding_windows': ('windows.py', 'def window_sums(values, window):\n    if window <= 0: raise ValueError("window")\n    xs = list(values)\n    return [sum(xs[i:i+window]) for i in range(len(xs)-window+1)]\n')}
            for name, (file, content) in fixes.items():
                work = (root / name / 'workspace').resolve()
                self.assertNotEqual(run_python(work, labels[name]['private_check'])['returncode'], 0)
                (work / file).write_text(content)
                self.assertTrue(run_python(work, tests=True)['tests_passed'])
                self.assertEqual(run_python(work, labels[name]['private_check'])['returncode'], 0)

    def test_release_dry_run_never_opens_docker_or_asks_key(self):
        with patch('scripts.run_release_check.subprocess.run') as run, patch('scripts.run_release_check.getpass.getpass') as key:
            self.assertEqual(main([]), 0)
            run.assert_not_called(); key.assert_not_called()

    def test_stale_image_stops_before_key_or_model_call(self):
        with patch('scripts.run_release_check.snapshot_checkout', return_value='commit'), \
             patch('scripts.run_release_check.fingerprint', return_value='expected'), \
             patch('scripts.run_release_check.subprocess.run') as run, \
             patch('scripts.run_release_check.getpass.getpass') as key:
            run.return_value.stdout = 'stale'
            with self.assertRaisesRegex(ValueError, 'image source'):
                main(['--live'])
            self.assertEqual(run.call_count, 2)
            self.assertIn('--network', run.call_args.args[0])
            key.assert_not_called()


if __name__ == '__main__':
    unittest.main()
