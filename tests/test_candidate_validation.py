import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.run_candidate_validation import main,STAGES
from scripts.run_challenge_benchmark import docker_command


class CandidateValidationTests(unittest.TestCase):
    def test_dry_run_never_starts_docker_or_requests_key(self):
        with patch('scripts.run_candidate_validation.subprocess.run') as run,patch('scripts.run_candidate_validation.getpass.getpass') as key,contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([]),0)
            run.assert_not_called();key.assert_not_called()
        self.assertIn('ceiling17000',output.getvalue())
        self.assertEqual(sum(stage[4] for stage in STAGES),17000)

    def test_regression_command_uses_release_suite_with_all_partition(self):
        cmd=docker_command('pinned',Path('/snapshot'),Path('/reports'),'all',5000,'plain',compact_data_context=True,suite='release')
        self.assertEqual(cmd[cmd.index('--suite')+1],'release')
        self.assertEqual(cmd[cmd.index('--partition')+1],'all')
        self.assertIn('--compact-data-context',cmd)
        self.assertIn('--release-defaults',cmd)
        self.assertNotIn('5000',cmd[:cmd.index('--entrypoint')])

    def test_complete_stages_and_stop_on_uncertain_usage(self):
        for complete in (True,False):
            with tempfile.TemporaryDirectory() as temp:
                repo=Path(temp);calls=[]
                def docker(command,**kwargs):
                    calls.append(command)
                    if len(calls)==1:return SimpleNamespace(stdout='sha256:pinned',returncode=0)
                    if len(calls)==2:return SimpleNamespace(stdout='fingerprint',returncode=0)
                    suite=command[command.index('--suite')+1];budget=int(command[command.index('--budget')+1])
                    count=40 if suite=='challenge' else 21
                    mount=next(x for x in command if x.startswith('type=bind,source=') and x.endswith('target=/results'))
                    target=Path(mount.split('source=',1)[1].split(',target=',1)[0])
                    summary=dict(tasks=count,budget=budget,weighted_tokens=100,usage_complete=complete,
                                 usage_uncertain=not complete,agent_exit_code=0,compact_data_context=True,json_mode=False)
                    (target/'benchmark.json').write_text(json.dumps({'summary':summary}))
                    return SimpleNamespace(returncode=0)
                with patch('scripts.run_candidate_validation.REPO',repo),patch('scripts.run_candidate_validation.snapshot_checkout',return_value='frozen'),patch('scripts.run_candidate_validation.fingerprint',return_value='fingerprint'),patch('scripts.run_candidate_validation.subprocess.run',side_effect=docker),patch.dict(os.environ,{'LLM_API_KEY':'not-a-real-key'}),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['--live']),0 if complete else 1)
                self.assertEqual(len(calls),4 if complete else 3)
                validation=json.loads(next(repo.glob('artifacts/*/validation.json')).read_text())
                self.assertEqual(validation['usage_complete'],complete)
                self.assertEqual(validation['max_series_budget'],17000)
                self.assertIn('confirmation',validation['stages'])
                if complete:self.assertIn('regression',validation['stages'])
                self.assertTrue(all('--compact-data-context' in cmd for cmd in calls[2:]))
                self.assertNotIn('not-a-real-key',json.dumps(validation))
                self.assertNotIn('not-a-real-key',json.dumps(calls))

    def test_stale_image_stops_before_key_or_paid_request(self):
        with patch('scripts.run_candidate_validation.snapshot_checkout',return_value='frozen'),patch('scripts.run_candidate_validation.fingerprint',return_value='expected'),patch('scripts.run_candidate_validation.subprocess.run') as run,patch('scripts.run_candidate_validation.getpass.getpass') as key,contextlib.redirect_stdout(io.StringIO()):
            run.return_value.stdout='stale'
            with self.assertRaisesRegex(ValueError,'image runtime differs'):main(['--live'])
            self.assertEqual(run.call_count,2);key.assert_not_called()
            self.assertIn('none',run.call_args.args[0])


if __name__=='__main__':unittest.main()
