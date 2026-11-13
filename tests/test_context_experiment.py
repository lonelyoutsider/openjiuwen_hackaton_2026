import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.run_context_experiment import main
from scripts.evaluate_examples import reported_run_usage


class ContextExperimentTests(unittest.TestCase):
    def test_pair_reports_profiles_and_stops_after_first_uncertain_arm(self):
        for completed in (True,False):
            with tempfile.TemporaryDirectory() as temp:
                repo=Path(temp);commands=[]
                def docker(command,**kwargs):
                    commands.append(command)
                    if len(commands)==1:return SimpleNamespace(stdout='sha256:image',returncode=0)
                    if len(commands)==2:return SimpleNamespace(stdout='fingerprint',returncode=0)
                    mount=next(x for x in command if x.startswith('type=bind,source=') and x.endswith('target=/results'))
                    target=Path(mount.split('source=',1)[1].split(',target=',1)[0])
                    summary={'tasks':60,'budget':12000,'weighted_tokens':10,'usage_complete':completed,
                        'usage_uncertain':not completed,'agent_exit_code':0,'compact_data_context':'--compact-data-context' in command}
                    (target/'benchmark.json').write_text(json.dumps({'summary':summary}))
                    return SimpleNamespace(returncode=0)
                with patch('scripts.run_context_experiment.REPO',repo),patch('scripts.run_context_experiment.snapshot_checkout',return_value='frozen'),patch('scripts.run_context_experiment.fingerprint',return_value='fingerprint'),patch('scripts.run_context_experiment.subprocess.run',side_effect=docker),patch.dict(os.environ,{'LLM_API_KEY':'not-a-real-key'}),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['--live']),0 if completed else 1)
                self.assertEqual(len(commands),4 if completed else 3)
                pair=json.loads(next(repo.glob('artifacts/*/comparison.json')).read_text())
                self.assertEqual(pair['max_pair_budget'],24000)
                self.assertEqual(pair['usage_complete'],completed)
                self.assertFalse(pair['arms']['baseline']['summary']['compact_data_context'])
                if completed:self.assertTrue(pair['arms']['compact']['summary']['compact_data_context'])
                self.assertNotIn('not-a-real-key',json.dumps(pair))
                self.assertNotIn('not-a-real-key',json.dumps(commands))

    def test_cli_finally_emits_charged_usage_when_a_task_raises(self):
        import run_agent
        from harness.execution import execute as original_execute
        class Ledger:
            stopped=False
            charged=False
            def snapshot(self):
                return dict(llm_calls=int(self.charged),input_tokens=17 if self.charged else 0,
                    output_tokens=12 if self.charged else 0,weighted_tokens=13.7 if self.charged else 0,
                    usage_uncertain=False)
        ledger=Ledger()
        def injected(task,agent=None):
            if agent is None:return original_execute(task)
            ledger.charged=True
            raise RuntimeError('injected error after an accounted request')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'case';folder.mkdir()
            (folder/'task.json').write_text(json.dumps(dict(task_id='case',task_type='math',instruction='Compute a new task.',reward=1)))
            with patch.object(sys,'argv',['run_agent.py','--tasks-dir',str(root),'--engine','stdlib']),patch.dict(os.environ,{'LLM_API_KEY':'not-a-real-key'}),patch('harness.llm.Client',return_value=ledger),patch('run_agent.execute',side_effect=injected),contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaisesRegex(RuntimeError,'injected error'):
                    asyncio.run(run_agent.main())
            usage=reported_run_usage(output.getvalue())
            self.assertEqual(usage['weighted_tokens'],13.7)
            self.assertEqual(usage['llm_calls'],1)
            self.assertFalse(usage['usage_uncertain'])


if __name__=='__main__':unittest.main()
