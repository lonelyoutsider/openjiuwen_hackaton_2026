import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.agent import Agent
from harness.tasks import Task
from harness.tools import initial_context,run_python
from scripts.evaluate_examples import reported_run_usage
from scripts.run_context_experiment import main
from scripts.run_challenge_benchmark import docker_command


class ContextTests(unittest.TestCase):
    def test_short_data_and_python_sources_are_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'a.csv').write_text('x,y\n1,2\n');(root/'impl.py').write_text('def f():\n    return 1\n'*100)
            self.assertEqual(initial_context(root),initial_context(root,compact_data=True))

    def test_large_data_is_marked_but_full_file_remains_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'large.csv';data='id,amount\n'+''.join(f'{i},1\n' for i in range(1800))
            path.write_text(data);before=path.read_bytes()
            compact=initial_context(root,compact_data=True);baseline=initial_context(root)
            self.assertIn('PREVIEW TRUNCATED',compact)
            self.assertLess(len(compact),len(baseline)//3)
            self.assertNotIn('1799,1',compact)
            result=run_python(root,"import csv\nprint(sum(int(r['amount']) for r in csv.DictReader(open('large.csv'))))")
            self.assertEqual(result['stdout'].strip(),'1800')
            self.assertEqual(path.read_bytes(),before)

    def test_short_file_has_no_false_truncation_and_omitted_data_is_marked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'a.txt').write_text('a'*1024);(root/'b.csv').write_text('x\n5\n')
            self.assertNotIn('PREVIEW TRUNCATED',initial_context(root,compact_data=True))
            self.assertIn('CONTENTS OMITTED',initial_context(root,limit=1,compact_data=True))

    def test_replayed_actions_work_with_compact_context_without_claiming_live_quality(self):
        class Replay:
            def __init__(self):self.prompts=[]
            def complete(self,messages,max_tokens):
                self.prompts.append(json.dumps(messages))
                return json.dumps({'action':'python','code':"import csv\nprint(sum(int(r['amount']) for r in csv.DictReader(open('large.csv'))))"} if len(self.prompts)==1 else {'action':'answer','answer':'1800'})
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);work=root/'workspace';work.mkdir()
            (work/'large.csv').write_text('id,amount\n'+''.join(f'{i},1\n' for i in range(1800)))
            (root/'task.json').write_text(json.dumps(dict(task_id='fresh',task_type='data_analysis',instruction='Sum all amounts from large.csv.',reward=1)))
            client=Replay();result=Agent(client,compact_data_context=True).solve(Task.load(root))
            self.assertEqual(result.answer,'1800');self.assertIn('PREVIEW TRUNCATED',client.prompts[0])

    def test_final_ledger_can_be_recovered_from_sdk_log_noise(self):
        expected={'weighted_tokens':12,'usage_uncertain':False}
        text='SDK info\n{}\n'+json.dumps({'run_usage':expected})+'\n'
        self.assertEqual(reported_run_usage(text),expected)
        self.assertIsNone(reported_run_usage('not a complete report'))

    def test_only_treatment_gets_context_flag(self):
        args=('image',Path('/snapshot'),Path('/reports'),'calibration',12000,'plain')
        control=docker_command(*args);compact=docker_command(*args,compact_data_context=True)
        self.assertNotIn('--compact-data-context',control)
        self.assertEqual(compact,control+['--compact-data-context'])

    def test_pair_is_dry_and_budget_is_fixed_before_requests(self):
        with patch('scripts.run_context_experiment.subprocess.run') as run,patch('scripts.run_context_experiment.getpass.getpass') as key,contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main([]),0);run.assert_not_called();key.assert_not_called()
        self.assertIn('24000',out.getvalue())


if __name__=='__main__':unittest.main()
