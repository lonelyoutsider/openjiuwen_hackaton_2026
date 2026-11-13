#!/usr/bin/env python3
"""One bounded release check of the actual /app image; no live calls by default."""
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

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.run_edit_experiment import snapshot_checkout
from harness.provenance import fingerprint


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--image', default='its-ia:release')
    parser.add_argument('--budget', type=int, default=10000)
    args = parser.parse_args(argv)
    if args.budget <= 0:
        parser.error('budget must be positive')
    print(f'One image-default check: 21 diagnostic tasks; budget <= {args.budget}; no automatic retries.', flush=True)
    if not args.live:
        print('No API requests. Build the release image and add --live to run.')
        return 0
    env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix='its-ia-release-') as folder:
        snapshot = Path(folder)
        sha = snapshot_checkout(REPO, snapshot)
        image = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image],
                               check=True, capture_output=True, text=True).stdout.strip()
        expected = fingerprint(snapshot)
        actual = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
            '--tmpfs', '/tmp:rw,size=2g', '--workdir', '/app', '--entrypoint', 'python', image,
            '-c', "from harness.provenance import fingerprint; print(fingerprint('/app'))"],
            check=True, capture_output=True, text=True, timeout=30).stdout.strip()
        if actual != expected:
            raise ValueError('image source does not match this commit; rebuild before spending API tokens')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        reports = REPO / 'artifacts' / ('release-' + stamp + '-' + uuid.uuid4().hex[:8])
        reports.mkdir(parents=True, exist_ok=False)
        env['LLM_API_KEY'] = env.get('LLM_API_KEY') or getpass.getpass('API key from NeuralDeep (hidden): ').strip()
        if not env['LLM_API_KEY'] or any(c.isspace() for c in env['LLM_API_KEY']) or env['LLM_API_KEY'].upper().startswith(('NGU26-', 'НГУ-')):
            raise ValueError('use the account API key')
        env.setdefault('LLM_BASE_URL', 'https://api.neuraldeep.ru/v1')
        env.pop('LLM_MODEL', None)
        command = ['docker', 'run', '--rm', '--read-only', '--tmpfs', '/tmp:rw,size=2g',
            '--cpus', '8', '--memory', '16g', '--pids-limit', '512', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--workdir', '/app', '-e', 'HOME=/tmp',
            '-e', 'LLM_API_KEY', '-e', 'LLM_BASE_URL',
            '--mount', f'type=bind,source={snapshot},target=/repo,readonly',
            '--mount', f'type=bind,source={reports},target=/results', '--entrypoint', 'python', image,
            '/repo/scripts/evaluate_examples.py', '--suite', 'release', '--release-defaults',
            '--llm', '--budget', str(args.budget), '--diagnostics', '--quiet', '--report', '/results/release.json']
        print(f'Commit: {sha}; verified image fingerprint: {expected}', flush=True)
        print(f'Report: {reports / "release.json"}', flush=True)
        run = subprocess.run(command, cwd=REPO, env=env, timeout=960)
        report = reports / 'release.json'
        if not report.is_file():
            print('No complete report; do not automatically repeat a possibly charged run.', file=sys.stderr)
            return run.returncode or 1
        data = json.loads(report.read_text(encoding='utf-8'))
        data['provenance'] = {'source_commit': sha, 'image_id': image,
            'source_fingerprint': expected, 'runtime_entrypoint': '/app/run_agent.py',
            'budget_source': 'BUDGET environment variable', 'max_budget': args.budget,
            'automatic_retries': False, 'container_exit_code': run.returncode}
        report.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        summary = data.get('summary', {})
        return run.returncode or int(bool(summary.get('usage_uncertain') or summary.get('agent_exit_code')))


if __name__ == '__main__':
    raise SystemExit(main())
