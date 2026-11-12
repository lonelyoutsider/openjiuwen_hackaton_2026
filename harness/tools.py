"""Small local tools. Container isolation remains the security boundary."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile


def protected(path):
    return any(part.lower() in ("tests", "test") for part in path.parts) or path.name.lower().startswith("test") or path.name.lower().endswith("_test.py")


def safe_path(workspace, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("path must be relative to workspace")
    path = (workspace / relative).resolve()
    if not path.is_relative_to(workspace) or path.is_symlink():
        raise ValueError("path leaves workspace")
    return path


def file_hashes(workspace, tests_only=False):
    result = {}
    for path in sorted(workspace.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlinks are not supported")
        relative = path.relative_to(workspace)
        if "__pycache__" in relative.parts or not path.is_file():
            continue
        if tests_only and not protected(relative):
            continue
        result[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def edit_source(workspace, relative, old_text, new_text):
    """Atomically replace one unique literal block in an existing Python source."""
    path = safe_path(workspace, relative)
    if not path.is_file() or protected(path.relative_to(workspace)) or path.suffix != ".py":
        raise ValueError("edit supports existing non-test Python sources only")
    if not isinstance(old_text, str) or not old_text or not isinstance(new_text, str):
        raise ValueError("old_text must be nonempty; new_text must be a string")
    if old_text == new_text:
        raise ValueError("edit must change the source")
    if max(len(old_text), len(new_text)) > 100000:
        raise ValueError("edit text exceeds the source limit")
    with path.open(encoding="utf-8", newline="") as stream:
        source = stream.read(100001)
    if len(source) > 100000:
        raise ValueError("source exceeds the edit limit")
    start = source.find(old_text)
    if start < 0:
        raise ValueError("old_text not found; read the current source before retrying")
    if source.find(old_text, start + 1) >= 0:
        raise ValueError("old_text is ambiguous; include more surrounding text")
    candidate = source[:start] + new_text + source[start + len(old_text):]
    if len(candidate) > 100000:
        raise ValueError("edited source exceeds the source limit")
    try:
        compile(candidate, str(path), "exec")
    except (SyntaxError, ValueError) as error:
        raise ValueError("edit rejected: invalid Python syntax") from error
    fd, temporary = tempfile.mkstemp(prefix=".its-ia-edit-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


# This audit guard prevents accidental access outside task data, test edits,
# subprocess creation and network use by generated Python. It is not a general
# adversarial sandbox; the final evaluator's restricted container is required.
DRIVER = r'''
import sys, os, json, pathlib, io
root = pathlib.Path(sys.argv[1]).resolve()
stdlib = pathlib.Path(sys.base_prefix).resolve()
payload = json.load(sys.stdin)
def checked(value, write=False):
    if isinstance(value, int) or value is None: return
    p = pathlib.Path(os.fsdecode(value)).resolve()
    if write:
        if not p.is_relative_to(root): raise PermissionError('write outside workspace')
        rel = p.relative_to(root)
        if any(x.lower() in ('test','tests') for x in rel.parts) or p.name.lower().startswith('test') or p.name.lower().endswith('_test.py'):
            raise PermissionError('test files are read-only')
    elif not p.is_relative_to(root) and not p.is_relative_to(stdlib) and str(p) not in ('/dev/null','/dev/urandom'):
        raise PermissionError('read outside workspace')
def audit(event,args):
    if event == 'open':
        mode = args[1] or ''
        flags = args[2] if len(args)>2 else 0
        write = any(c in mode for c in 'wax+') or bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        checked(args[0],write)
    elif event.startswith(('socket.','subprocess.','ctypes.')) or event in ('os.system','os.fork','os.forkpty','os.exec','os.posix_spawn','os.symlink','os.link','os.chdir','os.chroot'):
        raise PermissionError('operation not available to task code')
    elif event in ('os.remove','os.rmdir','os.mkdir','os.chmod','os.truncate','os.utime'):
        checked(args[0],True)
    elif event in ('os.rename','os.replace'):
        checked(args[0],True); checked(args[1],True)
sys.addaudithook(audit)
if payload['mode']=='tests':
    import unittest
    suite=unittest.defaultTestLoader.discover('.',pattern='test*.py')
    count=suite.countTestCases()
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    print('ITS_IA_TEST_RESULT='+json.dumps({'count':count,'ok':result.wasSuccessful()}))
    sys.exit(0 if count>0 and result.wasSuccessful() else 1)
else:
    sys.path.insert(0,str(root))
    exec(compile(payload['code'],'<task-code>','exec'),{'__name__':'__main__'})
'''


def _limits():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**2, 2 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def run_python(workspace, code=None, *, tests=False, timeout=12):
    env = {name: value for name, value in os.environ.items() if name in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR")}
    env.update(HOME=str(workspace), PYTHONDONTWRITEBYTECODE="1")
    payload = {"mode": "tests" if tests else "code", "code": code}
    # Temporary files cap retained output even when a program prints in a loop.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen([sys.executable, "-I", "-B", "-c", DRIVER, str(workspace)],
            cwd=workspace, env=env, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
            start_new_session=os.name == "posix", preexec_fn=_limits if os.name == "posix" else None)
        try:
            process.communicate(json.dumps(payload).encode(), timeout=timeout)
            status = process.returncode
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.communicate()
            status = -1
        stdout.seek(0); stderr.seek(0)
        output = stdout.read(16000).decode("utf-8", "replace")
        errors = stderr.read(8000).decode("utf-8", "replace")
    passed = False
    if tests:
        matches = re.findall(r'^ITS_IA_TEST_RESULT=(\{[^\n]+\})$', output, re.M)
        if matches:
            detail = json.loads(matches[-1])
            passed = status == 0 and detail.get("ok") is True and detail.get("count", 0) > 0
    return {"returncode": status, "stdout": output, "stderr": errors, "tests_passed": passed}


def initial_context(workspace, limit=24000):
    parts, used = [], 0
    files = sorted(p for p in workspace.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    if len(files) > 1000:
        raise ValueError("workspace has too many files")
    for path in files:
        rel = path.relative_to(workspace)
        if path.is_symlink():
            raise ValueError("workspace contains symlinks")
        label = f"\nFILE {rel.as_posix()} ({path.stat().st_size} bytes)\n"
        text = ""
        if used < limit:
            try:
                with path.open(encoding="utf-8") as source:
                    text = source.read(min(8000, limit - used))
            except (UnicodeError, OSError):
                text = "[binary or unreadable; use local tools]"
        parts.append(label + text)
        used += len(text)
    return "".join(parts)


def publish_sources(original, candidate, before):
    """Copy only existing changed Python sources after tests succeed."""
    after = file_hashes(candidate)
    changes = [name for name in after if after[name] != before.get(name)]
    if any(name not in before or protected(Path(name)) or Path(name).suffix != ".py" for name in changes):
        raise ValueError("only existing Python source edits can be published")
    if set(before) - set(after):
        raise ValueError("workspace files were deleted")
    for name in changes:
        shutil.copy2(candidate / name, safe_path(original, name))
