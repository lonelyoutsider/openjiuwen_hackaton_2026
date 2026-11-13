import contextlib
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import os

from scripts.challenge_set import build_challenge_set
from scripts.evaluate_examples import check_answer
from scripts.run_challenge_benchmark import main, docker_command


class ChallengeBenchmarkTests(unittest.TestCase):
    def test_population_and_partition_counts(self):
        expected={'all':(100,80,313),'smoke':(28,24,108),'calibration':(60,48,195),'confirmation':(40,32,118)}
        groups={}
        for part,(count,solvable,reward) in expected.items():
            with tempfile.TemporaryDirectory() as temp:
                ls=build_challenge_set(temp,part)
                self.assertEqual(len(ls),count)
                self.assertEqual(sum(x['expected'] is not None for x in ls.values()),solvable)
                self.assertEqual(sum(x['reward'] for x in ls.values() if x['expected'] is not None),reward)
                self.assertEqual({x['task_type'] for x in ls.values()},{'math','search','data_analysis','coding'})
                groups[part]={x['validation_group'] for x in ls.values()}
        self.assertFalse(groups['calibration'] & groups['confirmation'])
        self.assertTrue(groups['smoke'] <= groups['calibration'])
        self.assertEqual(len(groups['all']),60)

    def test_agent_inputs_never_contain_oracles_or_partition_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            ls=build_challenge_set(temp)
            for path in Path(temp).glob('*/task.json'):
                raw=json.loads(path.read_text())
                self.assertEqual(set(raw),{'task_id','task_type','instruction','reward'})
            for name,label in ls.items():
                if label['task_type']=='coding' and label['expected'] is not None:
                    self.assertIn('reference_sources',label)
                self.assertTrue(all(c not in label['task_id'] for c in ('missing','coding','math','search')))

    def test_all_twenty_reference_coding_repairs_pass_and_mutants_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            ls=build_challenge_set(temp);count=0
            for name,label in ls.items():
                if label['task_type']!='coding' or label['expected'] is None:continue
                folder=Path(temp)/name;work=folder/'workspace'
                protected={p.name:p.read_bytes() for p in work.glob('test*.py')}
                (folder/'answer.txt').write_text('DONE')
                self.assertFalse(check_answer(folder,label),label['validation_group'])
                for rel,code in label['reference_sources'].items():(work/rel).write_text(code)
                self.assertTrue(check_answer(folder,label),label['validation_group'])
                self.assertEqual(protected,{p.name:p.read_bytes() for p in work.glob('test*.py')})
                count+=1
            self.assertEqual(count,20)

    def test_deterministic_manifest_rewards_and_nonidentical_mutations(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            la=build_challenge_set(a);lb=build_challenge_set(b)
            self.assertEqual(la,lb)
            for name in la:self.assertEqual((Path(a)/name/'task.json').read_bytes(),(Path(b)/name/'task.json').read_bytes())
            for group in {x['validation_group'] for x in la.values() if x['task_type']=='coding' and x['expected'] is not None}:
                names=[n for n,x in la.items() if x['validation_group']==group]
                files=[{p.name:p.read_text() for p in (Path(a)/n/'workspace').glob('*.py') if not p.name.startswith('test')} for n in names]
                self.assertNotEqual(files[0],files[1],group)

    def test_numeric_oracle_accepts_equivalent_formatting_and_rejects_wrong(self):
        with tempfile.TemporaryDirectory() as temp:
            ls=build_challenge_set(temp)
            for name,label in ls.items():
                if label['expected'] is None or label['task_type']=='coding':continue
                folder=Path(temp)/name
                (folder/'answer.txt').write_text(label['expected'])
                self.assertTrue(check_answer(folder,label),label['validation_group'])
                (folder/'answer.txt').write_text('unrelated incorrect value')
                self.assertFalse(check_answer(folder,label))

    def test_independently_calculated_math_and_data_answers(self):
        math={'weighted':['63/4','46/3'],'discount_tax':['115','138'],
              'capacity':['356','382'],'cycles':['112','138'],
              'shortest_path':['8','9'],'probability':['1/6','2/9'],
              'business_days':['2026-11-25','2026-11-27'],'coin_change':['9','11'],
              'linear_system':['18','21'],'subarray':['16','17']}
        data={'signed_revenue':['29.75','42.25'],'two_table_join':['13','18'],
              'dedup_events':['2','2'],'csv_quoting':['12','13'],'group_tie':['a','a'],
              'long_aggregate':['1876','1877'],'missing_values':['20','22'],
              'timezone':['2','2'],'nested_json':['19','{"total": 20}'],'utf8_bom_tsv':['11','12']}
        with tempfile.TemporaryDirectory() as temp:
            labels=build_challenge_set(temp)
            for item in labels.values():
                if item['expected'] is None:continue
                expected=(math if item['task_type']=='math' else data if item['task_type']=='data_analysis' else {}).get(item['family'])
                if expected is None:continue
                actual=item['expected'];want=expected[item['variant']]
                if item['check']=='exact_number':self.assertEqual(Decimal(actual),Decimal(want),item['family'])
                else:self.assertEqual(actual,want,item['family'])

    def test_json_answer_compares_structure_and_types_without_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);label={'check':'exact_json','expected':'{"total":20}'}
            for text,valid in [('{"total":20}',True),('{"total":20.0}',True),
                               ('{ "total" : 20 }',True),('{"total":true}',False),
                               ('{"total":20,"total":20}',False),('{"total":NaN}',False),
                               ('{"total":20,"other":0}',False),('20',False)]:
                (root/'answer.txt').write_text(text)
                self.assertEqual(check_answer(root,label),valid,text)

    def test_long_tail_record_is_beyond_both_preview_and_read_window(self):
        with tempfile.TemporaryDirectory() as temp:
            ls=build_challenge_set(temp)
            for name,label in ls.items():
                if label['family']=='long_tail':
                    data=(Path(temp)/name/'workspace/archive.txt').read_text()
                    self.assertGreater(data.index('registered owner'),16000)

    def test_default_runner_is_dry_with_documented_ceiling(self):
        with patch('scripts.run_challenge_benchmark.subprocess.run') as run,patch('scripts.run_challenge_benchmark.getpass.getpass') as key,contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([]),0)
            run.assert_not_called();key.assert_not_called()
            self.assertIn('28 tasks',output.getvalue());self.assertIn('total budget <= 8000',output.getvalue())

    def test_command_runs_image_agent_via_evaluator_and_does_not_expose_key(self):
        cmd=docker_command('sha256:pinned',Path('/frozen'),Path('/reports'),'smoke',8000,'plain')
        self.assertIn('--release-defaults',cmd)
        self.assertIn('/repo/scripts/evaluate_examples.py',cmd)
        self.assertEqual(cmd[cmd.index('--format')+1],'plain')
        self.assertEqual(cmd[cmd.index('--budget')+1],'8000')
        self.assertIn('LLM_API_KEY',cmd)
        self.assertFalse(any('sk-' in arg for arg in cmd))
        self.assertIn('--read-only',cmd)
        self.assertIn('type=bind,source=/frozen,target=/repo,readonly',cmd)

    def test_stale_image_aborts_before_key_and_paid_run(self):
        with patch('scripts.run_challenge_benchmark.snapshot_checkout',return_value='commit'),patch('scripts.run_challenge_benchmark.fingerprint',return_value='expected'),patch('scripts.run_challenge_benchmark.subprocess.run') as run,patch('scripts.run_challenge_benchmark.getpass.getpass') as key,contextlib.redirect_stdout(io.StringIO()):
            run.return_value.stdout='stale'
            with self.assertRaisesRegex(ValueError,'image runtime'):
                main(['--live'])
            self.assertEqual(run.call_count,2);key.assert_not_called()
            self.assertIn('none',run.call_args.args[0])

    def test_report_provenance_and_missing_usage_are_handled_without_retries(self):
        for valid in (True,False):
            with tempfile.TemporaryDirectory() as temp:
                repo=Path(temp);commands=[]
                def docker(command,**kwargs):
                    commands.append(command)
                    if len(commands)==1:return SimpleNamespace(stdout='sha256:image',returncode=0)
                    if len(commands)==2:return SimpleNamespace(stdout='fingerprint',returncode=0)
                    mounts=[x for x in command if x.startswith('type=bind,source=') and x.endswith('target=/results')]
                    target=Path(mounts[0].split('source=',1)[1].split(',target=',1)[0])
                    summary={'tasks':28,'budget':8000,'weighted_tokens':12.5,'usage_uncertain':False,'agent_exit_code':0} if valid else {}
                    (target/'benchmark.json').write_text(json.dumps({'summary':summary}))
                    return SimpleNamespace(returncode=0)
                with patch('scripts.run_challenge_benchmark.REPO',repo),patch('scripts.run_challenge_benchmark.snapshot_checkout',return_value='frozen-commit'),patch('scripts.run_challenge_benchmark.fingerprint',return_value='fingerprint'),patch('scripts.run_challenge_benchmark.subprocess.run',side_effect=docker),patch.dict(os.environ,{'LLM_API_KEY':'not-a-real-key'}),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['--live']),0 if valid else 1)
                self.assertEqual(len(commands),3)
                result=json.loads(next(repo.glob('artifacts/*/benchmark.json')).read_text())
                self.assertEqual(result['provenance']['source_commit'],'frozen-commit')
                self.assertEqual(result['provenance']['format'],'plain')
                self.assertEqual(result['provenance']['status'],'completed' if valid else 'error_or_uncertain_usage')
                self.assertNotIn('not-a-real-key',json.dumps(result))
                self.assertNotIn('not-a-real-key',json.dumps(commands))


if __name__=='__main__':unittest.main()
