#!/usr/bin/env python3
"""One prepaid-budget benchmark of the existing image. Dry run by default."""
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
from scripts.challenge_set import build_challenge_set, PARTITIONS, VERSION
from scripts.run_edit_experiment import snapshot_checkout


def docker_command(image, snapshot, reports, partition, budget, response_format, *, compact_data_context=False, suite='challenge'):
    if suite not in ('challenge','release'):raise ValueError('unsupported validation suite')
    command=['docker','run','--rm','--read-only','--tmpfs','/tmp:rw,size=2g',
        '--cpus','8','--memory','16g','--pids-limit','512','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--workdir','/app','-e','HOME=/tmp',
        '-e','LLM_API_KEY','-e','LLM_BASE_URL',
        '--mount',f'type=bind,source={snapshot},target=/repo,readonly',
        '--mount',f'type=bind,source={reports},target=/results',
        '--entrypoint','python',image,'/repo/scripts/evaluate_examples.py',
        '--suite',suite,'--partition',partition,'--format',response_format,
        '--release-defaults','--llm','--budget',str(budget),'--diagnostics','--quiet',
        '--report','/results/benchmark.json']
    if compact_data_context:command.append('--compact-data-context')
    return command


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--image',default='its-ia:release')
    parser.add_argument('--budget',type=int,default=8000)
    parser.add_argument('--partition',choices=PARTITIONS,default='smoke')
    parser.add_argument('--format',choices=['plain','auto','json'],default='plain')
    parser.add_argument('--compact-data-context',action='store_true')
    args=parser.parse_args(argv)
    if args.budget<=0:parser.error('budget must be positive')
    with tempfile.TemporaryDirectory() as temp:
        labels=build_challenge_set(Path(temp)/'tasks',args.partition)
    print(f'{VERSION}: {len(labels)} tasks, {sum(x["expected"] is not None for x in labels.values())} solvable; '
          f'available reward={sum(x["reward"] for x in labels.values() if x["expected"] is not None)}; '
          f'partition={args.partition}; format={args.format}; total budget <= {args.budget}; no repeats.',flush=True)
    if not args.live:
        print('No Docker or API requests. Add --live for exactly one run.');return 0
    with tempfile.TemporaryDirectory(prefix='its-ia-benchmark-') as folder:
        snapshot=Path(folder);sha=snapshot_checkout(REPO,snapshot)
        image=subprocess.run(['docker','image','inspect','--format','{{.Id}}',args.image],
                             check=True,capture_output=True,text=True).stdout.strip()
        expected=fingerprint(snapshot)
        actual=subprocess.run(['docker','run','--rm','--network','none','--read-only',
            '--tmpfs','/tmp:rw,size=2g','--workdir','/app','--entrypoint','python',image,
            '-c',"from harness.provenance import fingerprint; print(fingerprint('/app'))"],
            check=True,capture_output=True,text=True,timeout=30).stdout.strip()
        if actual!=expected:raise ValueError('image runtime differs from this checkout; do not run a stale image')
        env=os.environ.copy();env.pop('LLM_MODEL',None)
        env.setdefault('LLM_BASE_URL','https://api.neuraldeep.ru/v1')
        key=env.get('LLM_API_KEY') or getpass.getpass('API key from NeuralDeep (hidden): ').strip()
        if not key or any(c.isspace() for c in key) or key.upper().startswith(('NGU26-','НГУ-')):
            raise ValueError('use the account API key')
        env['LLM_API_KEY']=key
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        reports=REPO/'artifacts'/('challenge-'+stamp+'-'+uuid.uuid4().hex[:8]);reports.mkdir(parents=True)
        provenance={'benchmark':VERSION,'source_commit':sha,'image_id':image,'source_fingerprint':expected,
                    'partition':args.partition,'format':args.format,'max_budget':args.budget,
                    'model':'qwen3.8-27b-noreason','automatic_retries':False,'status':'incomplete'}
        provenance['compact_data_context']=args.compact_data_context
        run_path=reports/'run.json';run_path.write_text(json.dumps(provenance,indent=2),encoding='utf-8')
        print(f'Commit: {sha}; runtime fingerprint: {expected}; report: {reports/"benchmark.json"}',flush=True)
        try:
            result=subprocess.run(docker_command(image,snapshot,reports,args.partition,args.budget,args.format,
                                  compact_data_context=args.compact_data_context),
                                  cwd=REPO,env=env,timeout=3550)
            report=reports/'benchmark.json'
            if not report.is_file():
                provenance['status']='missing_report_usage_unknown';return result.returncode or 1
            data=json.loads(report.read_text(encoding='utf-8'));summary=data.get('summary',{})
            required=('tasks','budget','weighted_tokens','usage_uncertain','agent_exit_code')
            failed=bool(result.returncode or any(k not in summary for k in required)
                        or summary.get('tasks')!=len(labels) or summary.get('budget')!=args.budget
                        or summary.get('agent_exit_code') or summary.get('usage_uncertain')
                        or not isinstance(summary.get('weighted_tokens'),(int,float))
                        or summary.get('weighted_tokens',float('inf'))>args.budget)
            provenance.update(status='error_or_uncertain_usage' if failed else 'completed',container_exit_code=result.returncode)
            data['provenance']=dict(provenance)
            report.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            return int(failed)
        except subprocess.TimeoutExpired:
            provenance['status']='timeout_usage_unknown'
            print('Timed out; usage may have been charged. Do not repeat automatically.',file=sys.stderr)
            return 1
        finally:
            run_path.write_text(json.dumps(provenance,indent=2),encoding='utf-8')


if __name__=='__main__':raise SystemExit(main())
