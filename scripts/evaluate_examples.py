#!/usr/bin/env python3
"""Offline evaluator. References are withheld from the agent input copy."""
import argparse
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from harness.tools import run_python
from harness.profile import DEFAULT_MODEL, DEFAULT_CALLS, resolve_json_mode


def normalized_json(text):
    def object_pairs(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    def reject_constant(value):raise ValueError('nonfinite JSON number')
    def normalize(value):
        if isinstance(value,dict):return ('object',tuple(sorted((k,normalize(v)) for k,v in value.items())))
        if isinstance(value,list):return ('array',tuple(normalize(v) for v in value))
        return (type(value).__name__,value)
    return normalize(json.loads(text,object_pairs_hook=object_pairs,parse_float=Decimal,
                                parse_int=Decimal,parse_constant=reject_constant))


def check_answer(folder, label):
    answer = folder / 'answer.txt'
    if not answer.is_file() or label['expected'] is None:
        return False
    text = answer.read_text(encoding='utf-8').strip()
    if label['check'] == 'exact_int':
        try:
            return int(text) == int(label['expected'])
        except ValueError:
            return False
    if label['check'] == 'exact_number':
        try:
            value = Decimal(text)
            return value.is_finite() and value == Decimal(label['expected'])
        except InvalidOperation:
            return False
    if label['check'] == 'exact_str':
        return text == label['expected']
    if label['check'] == 'exact_json':
        try:return normalized_json(text)==normalized_json(label['expected'])
        except (ValueError,TypeError):return False
    if label['check'] == 'unittest' and text == 'DONE':
        work = (folder / 'workspace').resolve()
        public = run_python(work, tests=True)
        if not public['tests_passed']:
            return False
        if label.get('private_check'):
            return run_python(work, label['private_check'])['returncode'] == 0
        return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['openjiuwen', 'stdlib'], default='openjiuwen')
    parser.add_argument('--llm', action='store_true')
    parser.add_argument('--budget', type=int, default=3000)
    parser.add_argument('--suite', choices=['public', 'validation', 'coding-edit', 'release', 'challenge'], default='public')
    parser.add_argument('--partition', choices=['all','smoke','calibration','confirmation'], default='all')
    parser.add_argument('--format', choices=['auto','plain','json'], default='auto', help='image-profile JSON mode override; plain simulates an unfamiliar judging proxy payload')
    parser.add_argument('--release-defaults', action='store_true', help='invoke the image /app/run_agent.py with only tasks-dir and BUDGET env')
    parser.add_argument('--enable-edit', action='store_true')
    parser.add_argument('--recover-actions', action='store_true')
    parser.add_argument('--json-mode', action='store_true')
    parser.add_argument('--quiet', action='store_true', help='capture SDK logs; print case outcomes and summary')
    parser.add_argument('--only', help='comma-separated case IDs for a targeted experiment')
    parser.add_argument('--diagnostics', action='store_true')
    parser.add_argument('--report', type=Path, help='save a sanitized JSON report after the agent exits')
    args = parser.parse_args()
    if args.budget <= 0:
        parser.error('budget must be positive')
    if args.release_defaults and (not args.llm or args.engine != 'openjiuwen'):
        parser.error('release-defaults requires explicit --llm and openjiuwen')
    if args.partition != 'all' and args.suite != 'challenge':
        parser.error('partitions are supported only by challenge')
    if args.format != 'auto' and not args.release_defaults:
        parser.error('format override requires release-defaults')
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / 'tasks'
        if args.suite == 'public':
            source = REPO / 'examples/task-dir'
            labels = {p.parent.name: json.loads(p.read_text(encoding='utf-8')) for p in source.glob('*/task.json')}
            shutil.copytree(source, root)
        elif args.suite == 'validation':
            from scripts.validation_set import build_validation_set
            labels = build_validation_set(root)
        elif args.suite == 'coding-edit':
            from scripts.coding_edit_set import build_coding_edit_set
            labels = build_coding_edit_set(root)
        elif args.suite == 'release':
            from scripts.release_set import build_release_set
            labels = build_release_set(root)
        else:
            from scripts.challenge_set import build_challenge_set
            labels = build_challenge_set(root, args.partition)
        if args.only:
            selected = set(args.only.split(','))
            unknown = selected - set(labels)
            if unknown:
                parser.error('unknown task IDs: ' + ','.join(sorted(unknown)))
            for name in set(labels) - selected:
                shutil.rmtree(root / name)
            labels = {name: label for name, label in labels.items() if name in selected}
        for path in root.glob('*/task.json'):
            data = json.loads(path.read_text(encoding='utf-8'))
            data.pop('expected', None)
            path.write_text(json.dumps(data), encoding='utf-8')
        options = ['--budget', str(args.budget), '--time-limit', '300', '--max-calls-per-task', '4',
                   '--max-output-tokens', '1024'] if args.llm else ['--no-llm']
        if args.diagnostics:
            options += ['--diagnostics']
        options += ['--enable-edit' if args.enable_edit else '--no-enable-edit']
        options += ['--recover-actions' if args.recover_actions else '--no-recover-actions']
        options += ['--json-mode' if args.json_mode else '--no-json-mode']
        entrypoint = REPO / 'run_agent.py'
        child_env = os.environ.copy()
        if args.release_defaults:
            entrypoint = Path('/app/run_agent.py')
            if not entrypoint.is_file():
                parser.error('release-defaults must run inside the built Docker image')
            options = []
            if args.format != 'auto':
                options += ['--json-mode' if args.format == 'json' else '--no-json-mode']
            child_env['BUDGET'] = str(args.budget)
            if args.diagnostics:
                child_env['ITS_IA_DIAGNOSTICS'] = '1'
            else:
                child_env.pop('ITS_IA_DIAGNOSTICS', None)
        started = time.monotonic()
        command = [sys.executable, str(entrypoint), '--tasks-dir', str(root)]
        if not args.release_defaults:
            command += ['--engine', args.engine]
        run = subprocess.run([*command, *options], cwd='/app' if args.release_defaults else REPO,
                             env=child_env, timeout=3500 if args.release_defaults else 360,
                             capture_output=args.quiet, text=True)
        elapsed = time.monotonic() - started
        if args.quiet and run.returncode:
            print('\n'.join(((run.stderr or '') + (run.stdout or '')).splitlines()[-30:]), file=sys.stderr)
        rows = []
        for name, label in sorted(labels.items()):
            folder = root / name
            record_path = folder / 'its_ia_result.json'
            record = json.loads(record_path.read_text(encoding='utf-8')) if record_path.is_file() else {}
            answer_path = folder / 'answer.txt'
            answer = answer_path.read_text(encoding='utf-8').strip() if answer_path.is_file() else None
            correct = check_answer(folder, label)
            impossible = label['expected'] is None
            outcome = ('ABSTAIN' if answer is None else 'UNJUSTIFIED_ANSWER') if impossible else ('PASS' if correct else 'UNSOLVED')
            row = {'task_id': name, 'task_type': label['task_type'], 'correct': correct,
                   'known_solvable': not impossible, 'outcome': outcome,
                   'answer': answer, 'expected': label['expected'], 'reward': label['reward'],
                   'status': record.get('status', 'not_recorded'), 'reason': record.get('reason', ''),
                   'llm_calls': record.get('llm_calls', 0), 'weighted_tokens': record.get('weighted_tokens', 0),
                   'input_tokens': record.get('input_tokens', 0), 'output_tokens': record.get('output_tokens', 0),
                   'usage_uncertain': record.get('usage_uncertain', False)}
            for key in ('validation_group','family','variant','partition','stress'):
                if key in label:row[key]=label[key]
            if args.diagnostics:
                row['diagnostics'] = record.get('diagnostics', [])
            if label['task_type'] == 'coding':
                row['candidate_sources'] = {
                    str(p.relative_to(folder / 'workspace')): p.read_text(encoding='utf-8')
                    for p in sorted((folder / 'workspace').rglob('*.py'))
                    if not p.name.startswith('test') and p.stat().st_size < 100000}
            rows.append(row)
            print(f"{name}: {outcome}; calls={row['llm_calls']}; tokens={row['weighted_tokens']:.1f}; status={row['status']}", flush=True)
        summary = {'dataset': args.suite + '; not hidden score', 'engine': args.engine,
                   'enable_edit': True if args.release_defaults else args.enable_edit,
                   'recover_actions': True if args.release_defaults else args.recover_actions,
                   'json_mode': (resolve_json_mode(os.environ.get('LLM_BASE_URL', 'https://api.neuraldeep.ru/v1'),
                                 None if args.format == 'auto' else args.format == 'json')
                                 if args.release_defaults else args.json_mode),
                   'partition': args.partition, 'format_override': args.format,
                   'release_defaults': args.release_defaults,
                   'max_calls_per_task': DEFAULT_CALLS if args.release_defaults else 4,
                   'elapsed_seconds': round(elapsed, 3),
                   'model': os.environ.get('LLM_MODEL', DEFAULT_MODEL) if args.llm else None,
                   'budget': args.budget if args.llm else 0,
                   'correct': sum(r['correct'] for r in rows), 'tasks': len(rows),
                   'solvable_tasks': sum(r['known_solvable'] for r in rows),
                   'reward': sum(r['reward'] for r in rows if r['correct']),
                   'available_reward': sum(r['reward'] for r in rows if r['known_solvable']),
                   'missing_data_unanswered': sum(not r['known_solvable'] and r['answer'] is None for r in rows),
                   'missing_data_answered': sum(not r['known_solvable'] and r['answer'] is not None for r in rows),
                   'missing_data_explicit_abstentions': sum(not r['known_solvable'] and r['status'] == 'insufficient_data' for r in rows),
                   'false_abstentions': sum(r['known_solvable'] and r['status'] == 'insufficient_data' for r in rows),
                   'llm_calls': sum(r['llm_calls'] for r in rows),
                   'input_tokens': sum(r['input_tokens'] for r in rows),
                   'output_tokens': sum(r['output_tokens'] for r in rows),
                   'weighted_tokens': round(sum(r['weighted_tokens'] for r in rows), 4),
                   'usage_uncertain': any(r['usage_uncertain'] for r in rows),
                   'agent_exit_code': run.returncode}
        summary['by_type'] = {
            kind: {'tasks': len(group), 'solvable':sum(r['known_solvable'] for r in group),
                   'correct':sum(r['correct'] for r in group),
                   'reward':sum(r['reward'] for r in group if r['correct']),
                   'available_reward':sum(r['reward'] for r in group if r['known_solvable']),
                   'weighted_tokens':round(sum(r['weighted_tokens'] for r in group),1)}
            for kind in sorted({r['task_type'] for r in rows})
            for group in [[r for r in rows if r['task_type']==kind]]}
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps({'summary': summary, 'tasks': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    return run.returncode


if __name__ == '__main__':
    raise SystemExit(main())
