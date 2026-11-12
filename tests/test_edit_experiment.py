import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness.agent import Agent, SYSTEM
from harness.tasks import Task
from harness.tools import edit_source
from scripts.coding_edit_set import build_coding_edit_set
from scripts.evaluate_examples import check_answer
from scripts.run_edit_experiment import docker_command, main, snapshot_checkout


class FakeClient:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.prompts = []

    def complete(self, messages, max_tokens):
        self.prompts.append(json.loads(json.dumps(messages)))
        return json.dumps(next(self.actions))


def coding_fixture(root):
    work = root / 'workspace'
    work.mkdir()
    (work / 'numbers.py').write_text('def add(a, b):\n    return a - b\n', encoding='utf-8')
    (work / 'test_numbers.py').write_text('import unittest\nfrom numbers import add\n'
        'class T(unittest.TestCase):\n    def test_add(self): self.assertEqual(add(2, 3), 5)\n', encoding='utf-8')
    (root / 'task.json').write_text(json.dumps({'task_id': 'new', 'task_type': 'coding',
        'instruction': 'Repair addition.', 'reward': 1}), encoding='utf-8')
    return Task.load(root)


class EditToolTests(unittest.TestCase):
    def test_replaces_unique_block_preserving_other_bytes_and_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.py'
            path.write_bytes(b'# comment\r\ndef f():\r\n    return 1\r\n')
            edit_source(root, 'source.py', 'return 1', 'return 2')
            self.assertEqual(path.read_bytes(), b'# comment\r\ndef f():\r\n    return 2\r\n')
            self.assertEqual(list(root.glob('.its-ia-edit-*')), [])

    def test_invalid_edits_leave_original_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.py'
            source = 'x = "aaa"\ny = 1\nz = 1\n'
            cases = [('absent', 'present'), ('= 1', '= 2'), ('aa', 'b'), ('', 'x'),
                     ('y = 1', 'y = 1'), ('y = 1', 'y = ('), ('y = 1', 'x' * 100001), (None, 'x')]
            for old, new in cases:
                with self.subTest(old=old):
                    path.write_text(source)
                    with self.assertRaises(ValueError):
                        edit_source(root, 'source.py', old, new)
                    self.assertEqual(path.read_text(), source)

    def test_test_paths_new_files_and_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp)
            root = outer / 'workspace'; root.mkdir()
            for name in ['test_code.py', 'code_test.py', 'notes.txt']:
                (root / name).write_text('x = 1\n')
            (outer / 'outside.py').write_text('x = 1\n')
            for name in ['test_code.py', 'code_test.py', 'notes.txt', 'new.py', '../outside.py']:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    edit_source(root, name, 'x = 1', 'x = 2')
            self.assertEqual((outer / 'outside.py').read_text(), 'x = 1\n')

    def test_atomic_replace_failure_preserves_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / 'source.py'; path.write_text('x = 1\n')
            with patch('harness.tools.os.replace', side_effect=OSError('simulated failure')):
                with self.assertRaises(OSError):
                    edit_source(root, 'source.py', '1', '2')
            self.assertEqual(path.read_text(), 'x = 1\n')
            self.assertEqual(list(root.glob('.its-ia-edit-*')), [])


class EditAgentTests(unittest.TestCase):
    def test_edit_is_opt_in_and_default_prompt_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = coding_fixture(Path(tmp))
            client = FakeClient([dict(action='edit', path='numbers.py', old_text='a - b', new_text='a + b')])
            result = Agent(client, max_calls=1).solve(task)
            self.assertEqual(result.status, 'unsupported')
            self.assertEqual(client.prompts[0][0]['content'], SYSTEM)
            self.assertIn('a - b', (task.workspace() / 'numbers.py').read_text())

    def test_enabled_edit_is_verified_and_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = coding_fixture(Path(tmp))
            before = (task.workspace() / 'test_numbers.py').read_bytes()
            client = FakeClient([dict(action='edit', path='numbers.py', old_text='a - b', new_text='a + b')])
            result = Agent(client, enable_edit=True, diagnostics=True).solve(task)
            self.assertEqual((result.status, result.answer), ('solved', 'DONE'))
            self.assertIn('a + b', (task.workspace() / 'numbers.py').read_text())
            self.assertEqual((task.workspace() / 'test_numbers.py').read_bytes(), before)

    def test_failed_edit_does_not_publish_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = coding_fixture(Path(tmp))
            client = FakeClient([dict(action='edit', path='numbers.py', old_text='a - b', new_text='0')])
            result = Agent(client, max_calls=1, enable_edit=True).solve(task)
            self.assertEqual(result.status, 'unsupported')
            self.assertIn('a - b', (task.workspace() / 'numbers.py').read_text())

    def test_edit_rejects_tests_even_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = coding_fixture(Path(tmp))
            before = (task.workspace() / 'test_numbers.py').read_bytes()
            client = FakeClient([dict(action='edit', path='test_numbers.py', old_text='5', new_text='-1')])
            self.assertEqual(Agent(client, max_calls=1, enable_edit=True).solve(task).status, 'unsupported')
            self.assertEqual((task.workspace() / 'test_numbers.py').read_bytes(), before)


class EditSuiteTests(unittest.TestCase):
    def test_private_checks_are_not_task_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); labels = build_coding_edit_set(root)
            self.assertEqual(len(labels), 3)
            self.assertGreater(len((root / 'coding_ledger/workspace/money.py').read_text()), 3500)
            for name, label in labels.items():
                raw = json.loads((root / name / 'task.json').read_text())
                self.assertNotIn('private_check', raw)
                self.assertNotIn('validation_group', raw)
                self.assertTrue(label['private_check'])

    def test_reference_repairs_pass_independent_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); labels = build_coding_edit_set(root)
            work = root / 'coding_ledger/workspace'
            edit_source(work, 'money.py', '    return sum((line_amount(row) for row in rows), Decimal("0"))',
                '    total = Decimal("0")\n    for row in rows:\n'
                '        if row["kind"] not in ("charge", "refund"):\n            raise ValueError("kind")\n'
                '        total += line_amount(row) * (1 if row["kind"] == "charge" else -1)\n    return total')
            work = root / 'coding_intervals/workspace'
            edit_source(work, 'intervals.py', 'start < merged[-1][1]', 'start <= merged[-1][1]')
            edit_source(work, 'intervals.py', 'merged[-1][1] = end', 'merged[-1][1] = max(merged[-1][1], end)')
            work = root / 'coding_tags/workspace'
            edit_source(work, 'normalization.py', 'value.strip().lower()', '" ".join(value.split()).casefold()')
            edit_source(work, 'formatter.py', 'return ", ".join(sorted({normalize_tag(value) for value in values}))',
                'return ", ".join(dict.fromkeys(tag for tag in map(normalize_tag, values) if tag))')
            for name, label in labels.items():
                with self.subTest(name=name):
                    (root / name / 'answer.txt').write_text('DONE')
                    self.assertTrue(check_answer(root / name, label))

    def test_visible_only_interval_fix_fails_independent_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); labels = build_coding_edit_set(root)
            edit_source(root / 'coding_intervals/workspace', 'intervals.py', 'start < merged[-1][1]', 'start <= merged[-1][1]')
            (root / 'coding_intervals/answer.txt').write_text('DONE')
            self.assertFalse(check_answer(root / 'coding_intervals', labels['coding_intervals']))

    def test_evaluator_dry_pass_uses_fresh_suite_without_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.json'
            repo = Path(__file__).resolve().parents[1]
            run = subprocess.run([sys.executable, str(repo / 'scripts/evaluate_examples.py'),
                '--suite', 'coding-edit', '--engine', 'stdlib', '--quiet', '--enable-edit', '--report', str(report)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            summary = json.loads(report.read_text())['summary']
            self.assertEqual((summary['tasks'], summary['available_reward'], summary['llm_calls']), (3, 9, 0))
            self.assertTrue(summary['enable_edit'])


class PairedRunnerTests(unittest.TestCase):
    def run_fake_pair(self, uncertain=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            calls = []
            def launch(command, **kwargs):
                if command[1:3] == ['image', 'inspect']:
                    return subprocess.CompletedProcess(command, 0, stdout='sha256:fake-image\n')
                calls.append(command)
                mount = next(x for x in command if x.startswith('type=bind,source=') and x.endswith(',target=/results'))
                reports = Path(mount[len('type=bind,source='):-len(',target=/results')])
                arm = 'edit' if '--enable-edit' in command else 'baseline'
                summary = {'weighted_tokens': 10.0, 'usage_uncertain': uncertain, 'agent_exit_code': 0}
                (reports / (arm + '.json')).write_text(json.dumps({'summary': summary}))
                return subprocess.CompletedProcess(command, 0)
            with patch('scripts.run_edit_experiment.__file__', str(root / 'scripts/runner.py')), \
                 patch('scripts.run_edit_experiment.snapshot_checkout', return_value='a' * 40), \
                 patch('scripts.run_edit_experiment.subprocess.run', side_effect=launch), \
                 patch.dict('os.environ', {'LLM_API_KEY': 'FAKE_KEY_SENTINEL'}), \
                 contextlib.redirect_stdout(io.StringIO()):
                status = main(['--live'])
            comparison = next((root / 'artifacts').rglob('comparison.json'))
            text = comparison.read_text()
            self.assertNotIn('FAKE_KEY_SENTINEL', text)
            self.assertNotIn('FAKE_KEY_SENTINEL', json.dumps(calls))
            return status, calls, json.loads(text)

    def test_pair_runs_once_per_arm_and_records_total(self):
        status, calls, result = self.run_fake_pair()
        self.assertEqual((status, len(calls), result['status']), (0, 2, 'completed'))
        self.assertEqual(result['weighted_tokens'], 20.0)
        self.assertEqual(result['max_pair_budget'], 6000)
        self.assertTrue(all('sha256:fake-image' in command for command in calls))

    def test_uncertain_first_arm_prevents_second_paid_run(self):
        status, calls, result = self.run_fake_pair(uncertain=True)
        self.assertEqual((status, len(calls)), (1, 1))
        self.assertEqual(result['status'], 'stopped_after_error_or_uncertain_usage')
        self.assertIsNone(result['weighted_tokens'])
        self.assertFalse(result['usage_complete'])

    def test_commands_differ_only_by_edit_flag(self):
        args = ('its-ia:test', Path('/snapshot'), Path('/reports'))
        baseline = docker_command(*args, 'baseline', 3000)
        edit = docker_command(*args, 'edit', 3000)
        self.assertNotIn('--enable-edit', baseline)
        self.assertEqual([x.replace('/results/edit.json', '/results/baseline.json') for x in edit[:-1]], baseline)
        self.assertEqual(edit[-1], '--enable-edit')
        self.assertIn('LLM_API_KEY', baseline)

    def test_default_dry_run_never_requests_key_or_launches_process(self):
        with patch('scripts.run_edit_experiment.subprocess.run') as run, patch('getpass.getpass') as key, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]), 0)
            run.assert_not_called(); key.assert_not_called()

    def test_snapshot_excludes_untracked_secret_and_rejects_dirty_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'repo'; repo.mkdir()
            def git(*args):
                return subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, text=True)
            git('init', '-q'); git('config', 'user.name', 'Test'); git('config', 'user.email', 'test@example.invalid')
            (repo / 'tracked.py').write_text('x = 1\n'); git('add', 'tracked.py'); git('commit', '-qm', 'fixture')
            (repo / '.env').write_text('SECRET_SENTINEL')
            dest = Path(tmp) / 'snapshot'
            sha = snapshot_checkout(repo, dest)
            self.assertEqual(len(sha), 40)
            self.assertEqual(sorted(p.name for p in dest.iterdir()), ['tracked.py'])
            (repo / 'tracked.py').write_text('x = 2\n')
            with self.assertRaises(ValueError):
                snapshot_checkout(repo, Path(tmp) / 'other')


if __name__ == '__main__':
    unittest.main()
