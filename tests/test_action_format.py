import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.actions import parse_action
from harness.agent import Agent
from harness.llm import Client, LLMStopped
from scripts.run_edit_experiment import docker_command
from test_edit_experiment import coding_fixture


class ActionFormatTests(unittest.TestCase):
    def test_plain_and_fenced_json_keep_strict_mode(self):
        action = {'action': 'answer', 'answer': '17'}
        for text in [json.dumps(action), '```json\n' + json.dumps(action) + '\n```']:
            for recovery in [False, True]:
                with self.subTest(text=text, recovery=recovery):
                    self.assertEqual(parse_action(text, recover=recovery), (action, 'strict'))

    def test_commentary_is_opt_in(self):
        text = 'I computed the total.\n{"action":"answer","answer":"17"}'
        with self.assertRaises(ValueError):
            parse_action(text)
        self.assertEqual(parse_action(text, recover=True), ({'action': 'answer', 'answer': '17'}, 'recovered'))

    def test_terminal_fence_and_braces_inside_strings(self):
        action = {'action': 'python', 'code': 'print({"key": "}"})'}
        text = 'I will compute this.\n```json\n' + json.dumps(action) + '\n```'
        self.assertEqual(parse_action(text, recover=True), (action, 'recovered'))

    def test_fence_language_label_does_not_change_json_content(self):
        action = {'action': 'read', 'path': 'module.py'}
        for language in ['python', 'JSON', 'text', '', 'json']:
            text = 'The next action is:\n```' + language + '\n' + json.dumps(action) + '\n```'
            with self.subTest(language=language):
                self.assertEqual(parse_action(text, recover=True), (action, 'recovered'))

    def test_fence_does_not_allow_non_json_code_before_or_after_action(self):
        action = '{"action":"answer","answer":"17"}'
        invalid = ['Explanation\n```python\nprint(1)\n' + action + '\n```',
                   'Explanation\n```python\n' + action + '\nprint(1)\n```']
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_action(text, recover=True)

    def test_ambiguous_truncated_or_extra_content_is_not_repaired(self):
        action = '{"action":"answer","answer":"17"}'
        invalid = ['No action was produced.', action + '\n}', action + action,
            'Example {}\n' + action, 'prefix }\n' + action,
            'prefix ' + action[:-1], 'prefix ' + action + '\nDo something else.',
            '[' + action + ']', 'prefix {"action":"answer","answer":"1","answer":"2"}',
            'prefix {"action":"read","path":"x","extra":"y"}',
            'prefix {"action":"read","path":12}', 'prefix {"action":"undeclared"}',
            'prefix {"action":"write","path":"source.py"}']
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_action(text, recover=True)

    def test_recovery_preserves_exact_edit_strings(self):
        action = {'action': 'edit', 'path': 'source.py', 'old_text': 'x = "a\\nb"\n',
                  'new_text': 'x = "c\\nd"\n'}
        self.assertEqual(parse_action('I will apply this.\n' + json.dumps(action), recover=True)[0], action)


class RecoveryAgentTests(unittest.TestCase):
    def client(self, text):
        class Fake:
            calls = 0
            def complete(self, messages, max_tokens):
                self.calls += 1
                return text
        return Fake()

    def test_complete_action_after_commentary_executes_in_one_existing_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = coding_fixture(Path(tmp))
            text = 'The operator is wrong.\n' + json.dumps({'action': 'edit', 'path': 'numbers.py',
                'old_text': 'a - b', 'new_text': 'a + b'})
            client = self.client(text)
            agent = Agent(client, max_calls=1, enable_edit=True, recover_actions=True, diagnostics=True)
            self.assertEqual(agent.solve(task).status, 'solved')
            self.assertEqual(client.calls, 1)
            self.assertEqual(agent.last_trace[0]['action_parse'], 'recovered')

    def test_recovery_cannot_enable_an_unavailable_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = coding_fixture(Path(tmp))
            text = 'Apply this.\n' + json.dumps({'action': 'edit', 'path': 'numbers.py',
                'old_text': 'a - b', 'new_text': 'a + b'})
            agent = Agent(self.client(text), max_calls=1, recover_actions=True)
            self.assertEqual(agent.solve(task).status, 'unsupported')
            self.assertIn('a - b', (task.workspace() / 'numbers.py').read_text())

    def test_recovered_write_to_tests_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = coding_fixture(Path(tmp))
            tests = task.workspace() / 'test_numbers.py'; before = tests.read_bytes()
            text = 'Apply this.\n' + json.dumps({'action': 'write', 'path': 'test_numbers.py', 'content': 'pass\n'})
            agent = Agent(self.client(text), max_calls=1, recover_actions=True)
            self.assertEqual(agent.solve(task).status, 'unsupported')
            self.assertEqual(tests.read_bytes(), before)


class TelemetryTests(unittest.TestCase):
    def test_provider_json_mode_is_opt_in_and_charged_from_the_same_usage(self):
        for json_mode in [False, True]:
            with self.subTest(json_mode=json_mode):
                client = Client('https://api.neuraldeep.ru/v1', 'test-key', 3000, json_mode=json_mode)
                data = {'usage': {'prompt_tokens': 30, 'completion_tokens': 10},
                        'choices': [{'message': {'content': '{"action":"answer","answer":"OK"}'}}]}
                with patch.object(client.opener, 'open', return_value=io.BytesIO(json.dumps(data).encode())) as call:
                    client.complete([], 32)
                body = json.loads(call.call_args.args[0].data)
                self.assertEqual(body.get('response_format'), {'type': 'json_object'} if json_mode else None)
                self.assertEqual(client.snapshot()['weighted_tokens'], 13.0)
                self.assertEqual(client.last_response_metadata['json_mode'], json_mode)

    def test_metadata_records_finish_and_reasoning_without_extra_charges(self):
        client = Client('https://api.neuraldeep.ru/v1', 'test-key', 3000)
        data = {'usage': {'prompt_tokens': 30, 'completion_tokens': 32,
                         'completion_tokens_details': {'reasoning_tokens': 25}},
                'choices': [{'finish_reason': 'length', 'message': {'content': 'Only prose.'}}]}
        with patch.object(client.opener, 'open', return_value=io.BytesIO(json.dumps(data).encode())):
            client.complete([], 32)
        self.assertEqual(client.snapshot()['weighted_tokens'], 35.0)
        self.assertEqual(client.last_response_metadata['reasoning_tokens'], 25)
        self.assertEqual(client.last_response_metadata['finish_reason'], 'length')
        self.assertEqual(client.last_response_metadata['content_chars'], 11)
        self.assertTrue(client.last_request_metadata['request_sent'])
        self.assertNotIn('test-key', json.dumps(client.last_response_metadata))

    def test_reservation_stop_is_explained_without_a_request(self):
        client = Client('https://api.neuraldeep.ru/v1', 'test-key', 1)
        with patch.object(client.opener, 'open') as request, self.assertRaises(LLMStopped):
            client.complete([], 32)
        request.assert_not_called()
        self.assertFalse(client.last_request_metadata['request_sent'])
        self.assertEqual(client.last_request_metadata['remaining_weighted_tokens'], 1)
        self.assertGreater(client.last_request_metadata['reservation_weighted_tokens'], 1)

    def test_budget_stop_is_in_agent_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = coding_fixture(Path(tmp))
            client = Client('https://api.neuraldeep.ru/v1', 'test-key', 1)
            agent = Agent(client, diagnostics=True)
            with patch.object(client.opener, 'open') as request:
                self.assertEqual(agent.solve(task).status, 'budget_stop')
            request.assert_not_called()
            self.assertEqual(agent.last_trace[0]['outcome'], 'request_stopped')
            self.assertFalse(agent.last_trace[0]['request']['request_sent'])


class FormatComparisonTests(unittest.TestCase):
    def test_json_pair_changes_only_response_format_flag_on_the_requested_suite(self):
        args = ('image', Path('/snapshot'), Path('/reports'))
        text = docker_command(*args, 'text', 4000, comparison='json-mode', suite='validation')
        structured = docker_command(*args, 'json', 4000, comparison='json-mode', suite='validation')
        self.assertIn('--enable-edit', text)
        self.assertIn('--recover-actions', text)
        self.assertIn('validation', text)
        self.assertEqual([x.replace('/results/json.json', '/results/text.json') for x in structured[:-1]], text)
        self.assertEqual(structured[-1], '--json-mode')

    def test_format_pair_changes_only_recovery_and_keeps_edit_in_both_arms(self):
        args = ('image', Path('/snapshot'), Path('/reports'))
        strict = docker_command(*args, 'strict', 3000, comparison='action-format')
        recover = docker_command(*args, 'recover', 3000, comparison='action-format')
        self.assertIn('--enable-edit', strict)
        self.assertIn('--enable-edit', recover)
        self.assertNotIn('--recover-actions', strict)
        self.assertEqual([x.replace('/results/recover.json', '/results/strict.json') for x in recover[:-1]], strict)
        self.assertEqual(recover[-1], '--recover-actions')


if __name__ == '__main__':
    unittest.main()
