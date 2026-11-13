#!/usr/bin/env python3
"""Validate the selected compact profile: reserved40 then regression21; dry by default."""
import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from harness.provenance import fingerprint
from scripts.run_edit_experiment import snapshot_checkout
from scripts.run_challenge_benchmark import docker_command

STAGES=(('confirmation','challenge','confirmation',40,12000),
        ('regression','release','all',21,5000))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--image',default='its-ia:context-experiment')
    args=parser.parse_args(argv)
    print('Selected compact/plain profile: reserved40 <=12000, regression21 <=5000; '
          'series ceiling17000 weighted tokens; separate stage budgets; no retries.',flush=True)
    if not args.live:
        print('No Docker or API requests. Existing matching context-experiment image can be reused.');return 0
    with tempfile.TemporaryDirectory(prefix='its-ia-confirm-') as temporary:
        snapshot=Path(temporary);sha=snapshot_checkout(REPO,snapshot)
        image=subprocess.run(['docker','image','inspect','--format','{{.Id}}',args.image],
                             check=True,capture_output=True,text=True).stdout.strip()
        expected=fingerprint(snapshot)
        actual=subprocess.run(['docker','run','--rm','--network','none','--read-only',
            '--tmpfs','/tmp:rw,size=2g','--workdir','/app','--entrypoint','python',image,
            '-c',"from harness.provenance import fingerprint; print(fingerprint('/app'))"],
            check=True,capture_output=True,text=True,timeout=30).stdout.strip()
        if actual!=expected:raise ValueError('image runtime differs from this checkout; do not spend tokens on a stale image')
        env=os.environ.copy();env.pop('LLM_MODEL',None)
        env.setdefault('LLM_BASE_URL','https://api.neuraldeep.ru/v1')
        key=env.get('LLM_API_KEY') or getpass.getpass('API key from NeuralDeep (hidden): ').strip()
        if not key or any(c.isspace() for c in key) or key.upper().startswith(('NGU26-','НГУ-')):
            raise ValueError('use the account API key')
        env['LLM_API_KEY']=key
        reports=REPO/'artifacts'/('candidate-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
        reports.mkdir(parents=True)
        validation={'source_commit':sha,'image_id':image,'source_fingerprint':expected,
            'model':'qwen3.8-27b-noreason','format':'plain','compact_data_context':True,
            'max_calls_per_task':6,'automatic_retries':False,'max_series_budget':17000,
            'stages':{},'status':'incomplete'}
        print(f'Commit: {sha}; report directory: {reports}',flush=True)
        try:
            for name,suite,partition,count,budget in STAGES:
                stage_dir=reports/name;stage_dir.mkdir()
                print(f'Starting {name}; {count} tasks; budget <={budget}',flush=True)
                result=subprocess.run(docker_command(image,snapshot,stage_dir,partition,budget,'plain',
                    compact_data_context=True,suite=suite),cwd=REPO,env=env,timeout=3550)
                path=stage_dir/'benchmark.json'
                data=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
                summary=data.get('summary',{});tokens=summary.get('weighted_tokens')
                validation['stages'][name]={'budget':budget,'exit_code':result.returncode,'summary':summary}
                if data:
                    data['provenance']={k:validation[k] for k in ('source_commit','image_id','source_fingerprint',
                        'model','format','compact_data_context')}
                    data['provenance'].update(stage=name,budget=budget)
                    (reports/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                if (result.returncode or not summary or summary.get('agent_exit_code')
                    or not summary.get('usage_complete') or summary.get('usage_uncertain')
                    or summary.get('tasks')!=count or summary.get('budget')!=budget
                    or summary.get('compact_data_context') is not True
                    or summary.get('json_mode') is not False
                    or type(tokens) not in (int,float) or not 0<=tokens<=budget):
                    validation['status']='stopped_after_error_or_uncertain_usage';return 1
            validation['status']='completed';return 0
        except subprocess.TimeoutExpired:
            validation['status']='timeout_usage_unknown';return 1
        finally:
            validation['reported_weighted_tokens']=round(sum(s['summary'].get('weighted_tokens',0)
                for s in validation['stages'].values() if type(s['summary'].get('weighted_tokens',0)) in (int,float)),1)
            validation['usage_complete']=validation['status']=='completed'
            validation['weighted_tokens']=validation['reported_weighted_tokens'] if validation['usage_complete'] else None
            (reports/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'Validation summary: {reports/"validation.json"}',flush=True)


if __name__=='__main__':raise SystemExit(main())
