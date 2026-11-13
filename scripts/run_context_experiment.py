#!/usr/bin/env python3
"""One A/B pair: shared SDK timeout fix, short marked data previews only in treatment."""
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


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--image',default='its-ia:context-experiment')
    parser.add_argument('--budget-per-arm',type=int,default=12000)
    parser.add_argument('--order',choices=['baseline-first','compact-first'],default='baseline-first')
    args=parser.parse_args(argv)
    if args.budget_per_arm<=0:parser.error('budget must be positive')
    print(f'One A/B pair, calibration60/plain; <= {args.budget_per_arm*2} weighted tokens total; '
          '6 calls/task, output cap1024, no retries. SDK timeout fix is common to both arms.',flush=True)
    if not args.live:
        print('No Docker or API requests. Build the candidate image and add --live.');return 0
    with tempfile.TemporaryDirectory(prefix='its-ia-context-') as temporary:
        snapshot=Path(temporary);sha=snapshot_checkout(REPO,snapshot)
        image=subprocess.run(['docker','image','inspect','--format','{{.Id}}',args.image],
                             check=True,capture_output=True,text=True).stdout.strip()
        expected=fingerprint(snapshot)
        actual=subprocess.run(['docker','run','--rm','--network','none','--read-only',
            '--tmpfs','/tmp:rw,size=2g','--workdir','/app','--entrypoint','python',image,
            '-c',"from harness.provenance import fingerprint; print(fingerprint('/app'))"],
            check=True,capture_output=True,text=True,timeout=30).stdout.strip()
        if actual!=expected:raise ValueError('rebuild the context-experiment image; source fingerprint differs')
        env=os.environ.copy();env.pop('LLM_MODEL',None)
        env.setdefault('LLM_BASE_URL','https://api.neuraldeep.ru/v1')
        key=env.get('LLM_API_KEY') or getpass.getpass('API key from NeuralDeep (hidden): ').strip()
        if not key or any(c.isspace() for c in key) or key.upper().startswith(('NGU26-','НГУ-')):
            raise ValueError('use the account API key')
        env['LLM_API_KEY']=key
        reports=REPO/'artifacts'/('context-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
        reports.mkdir(parents=True)
        order=['baseline','compact'] if args.order=='baseline-first' else ['compact','baseline']
        pair={'source_commit':sha,'image_id':image,'source_fingerprint':expected,
              'model':'qwen3.8-27b-noreason','suite':'challenge-v1/calibration; not hidden score',
              'format':'plain','shared_sdk_timeout_fix':True,'max_calls_per_task':6,
              'budget_per_arm':args.budget_per_arm,'max_pair_budget':2*args.budget_per_arm,
              'order':order,'automatic_retries':False,'arms':{},'status':'incomplete'}
        print(f'Commit: {sha}; report directory: {reports}',flush=True)
        try:
            for arm in order:
                arm_dir=reports/arm;arm_dir.mkdir()
                print(f'Starting {arm}; report {reports/(arm+".json")}',flush=True)
                result=subprocess.run(docker_command(image,snapshot,arm_dir,'calibration',args.budget_per_arm,'plain',
                    compact_data_context=arm=='compact'),env=env,cwd=REPO,timeout=3550)
                path=arm_dir/'benchmark.json'
                data=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
                summary=data.get('summary',{})
                pair['arms'][arm]={'exit_code':result.returncode,'summary':summary}
                if data:
                    data['provenance']={k:pair[k] for k in ('source_commit','image_id','source_fingerprint','model','format')}
                    data['provenance'].update(arm=arm,compact_data_context=arm=='compact')
                    (reports/(arm+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                tokens=summary.get('weighted_tokens')
                if (result.returncode or not summary or summary.get('agent_exit_code')
                    or not summary.get('usage_complete') or summary.get('usage_uncertain')
                    or summary.get('tasks')!=60 or summary.get('budget')!=args.budget_per_arm
                    or summary.get('compact_data_context')!=(arm=='compact')
                    or type(tokens) not in (int,float) or not 0<=tokens<=args.budget_per_arm):
                    pair['status']='stopped_after_error_or_uncertain_usage';return 1
            pair['status']='completed';return 0
        except subprocess.TimeoutExpired:
            pair['status']='timeout_usage_unknown';return 1
        finally:
            pair['reported_weighted_tokens']=round(sum(a['summary'].get('weighted_tokens',0)
                for a in pair['arms'].values() if type(a['summary'].get('weighted_tokens',0)) in (int,float)),1)
            pair['usage_complete']=pair['status']=='completed'
            pair['weighted_tokens']=pair['reported_weighted_tokens'] if pair['usage_complete'] else None
            (reports/'comparison.json').write_text(json.dumps(pair,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'Pair summary: {reports/"comparison.json"}',flush=True)


if __name__=='__main__':raise SystemExit(main())
