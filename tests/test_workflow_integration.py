"""Real SDK, local fake provider; validates plumbing, not LLM quality."""
import http.server
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


@unittest.skipUnless(importlib.util.find_spec("openjiuwen"), "openJiuwen not installed")
class WorkflowIntegrationTests(unittest.TestCase):
    def test_real_workflow_against_local_fake_provider(self):
        self._run_workflow(enable_edit=False)

    def test_real_workflow_routes_edit_flag_and_runs_tests(self):
        self._run_workflow(enable_edit=True)

    def test_real_workflow_recovers_complete_action_after_commentary(self):
        self._run_workflow(enable_edit=True, recover_actions=True)

    def test_real_workflow_forwards_provider_json_mode(self):
        self._run_workflow(enable_edit=True, json_mode=True)

    def test_judge_style_command_uses_release_defaults_and_budget_env(self):
        self._run_workflow(enable_edit=True, recover_actions=True, judge_style=True)

    def test_judge_style_small_budget_adapts_output_allowance(self):
        self._run_workflow(enable_edit=True, recover_actions=True, judge_style=True, budget=1000)

    def test_judge_style_command_overrides_short_sdk_default(self):
        self._run_workflow(enable_edit=True,recover_actions=True,judge_style=True,sdk_timeout='0.001')

    def _run_workflow(self, enable_edit, recover_actions=False, json_mode=False, judge_style=False, budget=5000, sdk_timeout=None):
        output_caps = []
        class Provider(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                output_caps.append(request['max_tokens'])
                if request.get('response_format') != ({'type': 'json_object'} if json_mode else None):
                    raise AssertionError('JSON mode did not reach the provider as configured')
                messages = request["messages"]
                if "Task type: coding" in messages[1]["content"]:
                    if enable_edit:
                        if "Additional coding action:" not in messages[0]["content"]:
                            raise AssertionError("edit flag did not reach the workflow agent")
                        action = {"action": "edit", "path": "mylib.py", "old_text": "a-b", "new_text": "a+b"}
                    else:
                        action = {"action": "write", "path": "mylib.py", "content": "def add(a,b):\n    return a+b\n"}
                elif len(messages) > 2:
                    action = {"action": "answer", "answer": "51"}
                else:
                    action = {"action": "python", "code": "print(17*3)"}
                text = json.dumps(action)
                if recover_actions:
                    text = "I have selected the following action.\n" + text
                data = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 200, "completion_tokens": 100,
                                  "completion_tokens_details": {"reasoning_tokens": 5}}}
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            math = root / "math"; math.mkdir()
            (math / "task.json").write_text(json.dumps({"task_id": "math", "task_type": "math",
                "instruction": "Three crates contain 17 apples each. How many apples altogether?", "reward": 1}))
            coding = root / "coding"; coding.mkdir()
            work = coding / "workspace"; work.mkdir()
            (coding / "task.json").write_text(json.dumps({"task_id": "coding", "task_type": "coding",
                "instruction": "Fix addition, preserve tests", "reward": 2}))
            (work / "mylib.py").write_text("def add(a,b):\n    return a-b\n")
            tests = "import unittest\nfrom mylib import add\nclass T(unittest.TestCase):\n    def test_add(self): self.assertEqual(add(2,3),5)\n"
            (work / "test_mylib.py").write_text(tests)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            env = os.environ.copy()
            env.update(LLM_BASE_URL=f"http://127.0.0.1:{server.server_port}/v1", LLM_API_KEY="fake-integration-key")
            env['BUDGET'] = str(budget)
            if sdk_timeout is not None:env['WORKFLOW_EXECUTE_TIMEOUT']=sdk_timeout
            repo = Path(__file__).resolve().parents[1]
            try:
                flags = [] if judge_style else ["--budget", "5000", "--diagnostics",
                    "--enable-edit" if enable_edit else "--no-enable-edit",
                    "--recover-actions" if recover_actions else "--no-recover-actions",
                    "--json-mode" if json_mode else "--no-json-mode"]
                run = subprocess.run([sys.executable, str(repo / "run_agent.py"), "--tasks-dir", str(root), *flags],
                    env=env, capture_output=True, text=True, timeout=90)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr[-3000:] + run.stdout[-3000:])
            self.assertEqual((math / "answer.txt").read_text().strip(), "51")
            self.assertEqual((coding / "answer.txt").read_text().strip(), "DONE")
            self.assertEqual((work / "test_mylib.py").read_text(), tests)
            record = json.loads((coding / "its_ia_result.json").read_text())
            self.assertEqual(record["llm_calls"], 1)
            self.assertEqual(record["weighted_tokens"], 120)
            self.assertEqual(record["backend"], "llm")
            if budget == 1000:
                self.assertTrue(output_caps)
                self.assertTrue(all(64 <= cap < 1024 for cap in output_caps))
            if not judge_style:
                self.assertEqual(record["diagnostics"][0]["api"]["finish_reason"], "stop")
                self.assertEqual(record["diagnostics"][0]["api"]["reasoning_tokens"], 5)
                self.assertEqual(record["diagnostics"][0]["action_parse"], "recovered" if recover_actions else "strict")


if __name__ == "__main__":
    unittest.main()
