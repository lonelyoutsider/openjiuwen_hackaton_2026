import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from harness.agent import Agent
from harness.llm import Client, LLMStopped
from harness.tasks import Task
from harness.tools import run_python


class FakeClient:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.prompts = []

    def complete(self, messages, max_tokens):
        self.prompts.append(json.dumps(messages))
        return json.dumps(next(self.actions))


def task_fixture(root, *, tests=True):
    work = root / "workspace"
    work.mkdir()
    (work / "mylib.py").write_text("def add(a,b):\n    return a-b\n")
    if tests:
        (work / "test_mylib.py").write_text(
            "import unittest\nfrom mylib import add\nclass T(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(add(2,3),5)\n        self.assertEqual(add(-1,4),3)\n")
    (root / "task.json").write_text(json.dumps({"task_id": "custom", "task_type": "coding",
        "instruction": "Fix add, preserve tests.", "reward": 2, "expected": "FORBIDDEN_LABEL"}))
    return Task.load(root)


class LedgerTests(unittest.TestCase):
    def client(self, budget=3000):
        return Client("https://api.neuraldeep.ru/v1", "test-token", budget)

    def test_verified_usage_and_reasoning_not_counted_twice(self):
        client = self.client()
        data = {"usage": {"prompt_tokens": 17, "completion_tokens": 2,
                         "completion_tokens_details": {"reasoning_tokens": 1}},
                "choices": [{"message": {"content": "OK"}}]}
        with patch.object(client.opener, "open", return_value=io.BytesIO(json.dumps(data).encode())):
            self.assertEqual(client.complete([], 32), "OK")
        self.assertEqual(client.snapshot()["weighted_tokens"], 3.7)
        self.assertEqual(client.calls, 1)

    def test_budget_refusal_sends_no_request(self):
        client = self.client(budget=1)
        with patch.object(client.opener, "open") as request:
            with self.assertRaises(LLMStopped):
                client.complete([], 32)
            request.assert_not_called()
        self.assertEqual(client.calls, 0)

    def test_network_failure_retains_reservation_and_stops_retries(self):
        client = self.client()
        with patch.object(client.opener, "open", side_effect=urllib.error.URLError("secret-provider-body")) as request:
            for _ in range(2):
                with self.assertRaises(LLMStopped) as error:
                    client.complete([], 32)
                self.assertNotIn("secret-provider-body", str(error.exception))
            request.assert_called_once()
        self.assertTrue(client.snapshot()["usage_uncertain"])
        self.assertGreater(client.spent, 0)

    def test_missing_usage_stops_further_calls(self):
        client = self.client()
        with patch.object(client.opener, "open", return_value=io.BytesIO(b'{}')):
            with self.assertRaises(LLMStopped):
                client.complete([], 32)
        self.assertTrue(client.stopped)


class AgentTests(unittest.TestCase):
    def test_invalid_write_is_feedback_then_corrected_source_can_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            task=task_fixture(Path(temp))
            client=FakeClient([{'action':'write','path':'mylib.py','content':'def broken(:'},
                               {'action':'write','path':'mylib.py','content':'def add(a,b):\n    return a+b\n'}])
            agent=Agent(client,diagnostics=True)
            result=agent.solve(task)
            self.assertEqual(result.status,'solved')
            self.assertIn('SyntaxError',agent.last_trace[0]['observation'])

    def test_diagnostics_include_action_and_action_error_without_system_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            task = task_fixture(Path(temp))
            client = FakeClient([{'action': 'read', 'path': 'missing.csv'},
                                 {'action': 'abstain', 'reason': 'required file is absent'}])
            agent = Agent(client, max_calls=2, diagnostics=True)
            self.assertEqual(agent.solve(task).status, 'insufficient_data')
            self.assertEqual(len(agent.last_trace), 2)
            self.assertIn('FileNotFoundError', agent.last_trace[0]['observation'])
            self.assertNotIn('You solve a single local task', json.dumps(agent.last_trace))
            self.assertIn('FINAL available call', client.prompts[-1])
            self.assertEqual(len(client.prompts), 2)

    def test_diagnostics_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            task = task_fixture(Path(temp))
            agent = Agent(FakeClient([{'action': 'abstain', 'reason': 'test'}]))
            agent.solve(task)
            self.assertEqual(agent.last_trace, [])

    def test_malformed_action_consumes_only_the_configured_attempts(self):
        with tempfile.TemporaryDirectory() as temp:
            task = task_fixture(Path(temp))
            client = FakeClient([])
            client.complete = lambda messages, max_tokens: "```"
            self.assertEqual(Agent(client, max_calls=1).solve(task).status, "unsupported")

    def test_coding_fix_verified_and_published_without_label(self):
        with tempfile.TemporaryDirectory() as temp:
            task = task_fixture(Path(temp))
            tests = (task.workspace() / "test_mylib.py").read_bytes()
            client = FakeClient([{"action": "write", "path": "mylib.py", "content": "def add(a,b):\n    return a+b\n"}])
            result = Agent(client).solve(task)
            self.assertEqual((result.status, result.answer), ("solved", "DONE"))
            self.assertIn("return a+b", (task.workspace() / "mylib.py").read_text())
            self.assertEqual(tests, (task.workspace() / "test_mylib.py").read_bytes())
            self.assertNotIn("FORBIDDEN_LABEL", client.prompts[0])

    def test_failed_candidate_does_not_modify_original(self):
        with tempfile.TemporaryDirectory() as temp:
            task = task_fixture(Path(temp))
            before = (task.workspace() / "mylib.py").read_bytes()
            client = FakeClient([{"action": "write", "path": "mylib.py", "content": "def add(a,b):\n    return 0\n"}])
            self.assertEqual(Agent(client, max_calls=1).solve(task).status, "unsupported")
            self.assertEqual(before, (task.workspace() / "mylib.py").read_bytes())

    def test_test_edit_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            task = task_fixture(Path(temp))
            before = (task.workspace() / "test_mylib.py").read_bytes()
            client = FakeClient([{"action": "write", "path": "test_mylib.py", "content": "pass"}])
            self.assertEqual(Agent(client, max_calls=1).solve(task).status, "unsupported")
            self.assertEqual(before, (task.workspace() / "test_mylib.py").read_bytes())

    def test_no_tests_is_not_accepted_as_success(self):
        with tempfile.TemporaryDirectory() as temp:
            task = task_fixture(Path(temp), tests=False)
            client = FakeClient([{"action": "answer", "answer": "DONE"}])
            self.assertEqual(Agent(client, max_calls=1).solve(task).status, "unsupported")

    def test_new_math_wording_uses_python_tool_then_answer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "task.json").write_text(json.dumps({"task_id": "new", "task_type": "math", "reward": 1,
                "instruction": "What is the sum of the first 100 positive integers?"}))
            client = FakeClient([{"action": "python", "code": "print(sum(range(1,101)))"},
                                 {"action": "answer", "answer": "5050"}])
            result = Agent(client).solve(Task.load(root))
            self.assertEqual(result.answer, "5050")
            self.assertIn("5050", client.prompts[1])


class ToolBoundaryTests(unittest.TestCase):
    def test_network_is_denied(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run_python(Path(temp), "import socket; socket.socket()")
            self.assertNotEqual(result["returncode"], 0)
            self.assertIn("PermissionError", result["stderr"])

    def test_credentials_not_inherited(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"LLM_API_KEY": "PRIVATE_KEY_SENTINEL"}):
            result = run_python(Path(temp), "import os; print(os.environ.get('LLM_API_KEY'))")
            self.assertEqual(result["stdout"].strip(), "None")

    def test_read_outside_workspace_denied(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); work = root / "workspace"; work.mkdir()
            secret = root / "outside.txt"; secret.write_text("PRIVATE_DATA")
            result = run_python(work, f"print(open({str(secret)!r}).read())")
            self.assertNotEqual(result["returncode"], 0)
            self.assertNotIn("PRIVATE_DATA", result["stdout"])


if __name__ == "__main__":
    unittest.main()
