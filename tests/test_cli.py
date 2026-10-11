"""Real HTTP check of the standard-library uploader against a running app."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen


def test_live_upload_retry_zero_failure_and_conflict(tmp_path):
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = os.environ | {'DATABASE_URL': f'sqlite:///{tmp_path}/live.db', 'UPLOAD_TOKEN': 'live-test-token'}
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
                              cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                with urlopen(base + '/healthz', timeout=1):
                    break
            except OSError:
                assert server.poll() is None, 'HTTP server terminated before startup'
                time.sleep(.05)
        else:
            raise AssertionError('HTTP server did not start')
        client_env = os.environ | {'DEFECT_SERVER_URL': base, 'DEFECT_UPLOAD_TOKEN': 'live-test-token',
                                   'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost'}
        command = [sys.executable, str(root/'scripts/upload.py'), '--release', 'SVR27A', '--branch', 'REL COMMON',
                   '--part', 'Security', '--cl', '98765', '--uploader', 'skill']
        file = tmp_path / '한글.md';file.write_text('# 실제 HTTP 검증\n본문\n', encoding='utf-8')
        def send(*args):
            return subprocess.run(command + list(args), env=client_env, capture_output=True, text=True, timeout=15)
        first = send('--run-id', 'http-001', str(file))
        assert first.returncode == 0, first.stderr
        repeated = send('--run-id', 'http-001', str(file))
        assert repeated.returncode == 0 and json.loads(repeated.stdout)['duplicate'] is True
        file.write_text('# Changed\n', encoding='utf-8')
        conflict = send('--run-id', 'http-001', str(file))
        assert conflict.returncode == 1 and '409' in conflict.stderr
        assert send('--run-id', 'http-zero', '--no-findings').returncode == 0
        assert send('--run-id', 'http-failed', '--status', 'failed', '--error', 'timeout').returncode == 0
        with urlopen(base + '/api/runs') as response:
            assert json.load(response)['total'] == 3
    finally:
        server.terminate()
        server.wait(timeout=10)
