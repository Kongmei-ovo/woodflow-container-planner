"""Verify the real CI-built native package through download, probe, restart and old entry reuse."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from zipfile import ZipFile

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from container_planner import __version__
from container_planner.demo import load_demo
from container_planner.store import Store
from container_planner.updates import platform_label


def wait_health(root, expected):
    for _ in range(200):
        try:
            instance = json.loads((root / 'instance.json').read_text())
            with httpx.Client(base_url=instance['url'], timeout=2, trust_env=False) as client:
                if client.get('/api/health').json()['version'] == expected:
                    return instance
        except (OSError, ValueError, httpx.HTTPError):
            pass
        time.sleep(.2)
    raise RuntimeError('Native update did not reach expected version: ' + expected)


def stop(url):
    with httpx.Client(base_url=url, timeout=3, trust_env=False) as client:
        client.post('/api/shutdown').raise_for_status()
        for _ in range(100):
            try: client.get('/api/health')
            except httpx.HTTPError: break
            time.sleep(.1)
    time.sleep(.5)


if __name__ == '__main__':
    label = platform_label()
    archive = ROOT / 'dist/releases' / f'WoodFlow-{__version__}-{label}.zip'
    assert archive.is_file(), archive
    with tempfile.TemporaryDirectory(prefix='木序 更新验收-') as directory:
        root = Path(directory)
        marker = load_demo(Store(root))['project_id']
        launch = [sys.executable, str(ROOT / 'scripts/update_launch_fixture.py'), str(archive), __version__, label, '--data-dir', str(root), '--no-browser']
        old = subprocess.Popen(launch, cwd=ROOT)
        url = None
        try:
            initial = wait_health(root, '1.0.0-beta.1'); url = initial['url']
            with httpx.Client(base_url=url, timeout=60, trust_env=False) as client:
                client.post('/api/updates/check').raise_for_status()
                for _ in range(200):
                    state = client.get('/api/updates').json()
                    if state['status'] != 'checking': break
                    time.sleep(.05)
                assert state['status'] == 'available', state
                client.post('/api/updates/install', json={'version': __version__}).raise_for_status()
                for _ in range(600):
                    state = client.get('/api/updates').json()
                    if state['status'] not in {'downloading', 'verifying'}: break
                    time.sleep(.2)
                assert state['status'] == 'ready', state
                assert old.poll() is None, 'Preparing must keep the old app running'
                assert client.get('/api/projects/' + marker).status_code == 200
                client.post('/api/updates/restart').raise_for_status()
            current = wait_health(root, __version__)
            assert current['url'] == url and current['id'] != initial['id']
            old.wait(timeout=15)
            with httpx.Client(base_url=url, timeout=10, trust_env=False) as client:
                assert client.get('/api/projects/' + marker).status_code == 200
                backup = client.get('/api/updates/backup')
                backup.raise_for_status()
                with ZipFile(BytesIO(backup.content)) as zipped:
                    assert 'planner.sqlite3' in zipped.namelist()
            active = json.loads((root / 'updates/active.json').read_text())
            assert active['version'] == __version__
            stop(url); url = None
            # Double-clicking an older entry after quitting must reach the managed update.
            older = subprocess.run(launch, cwd=ROOT, timeout=15)
            assert older.returncode == 0
            current = wait_health(root, __version__); url = current['url']
            with httpx.Client(base_url=url, timeout=10, trust_env=False) as client:
                assert client.get('/api/projects/' + marker).status_code == 200
            print('PASS native updater: official URL selection → SHA256 download → extraction → isolated native preflight → backup → same-data restart → active pointer → old entry reopens updated app')
        except Exception:
            log = root / 'application.log'
            if log.exists(): print(log.read_text(encoding='utf-8', errors='replace')[-9000:])
            raise
        finally:
            if url:
                try: stop(url)
                except httpx.HTTPError: pass
            if old.poll() is None:
                old.terminate(); old.wait(timeout=10)
