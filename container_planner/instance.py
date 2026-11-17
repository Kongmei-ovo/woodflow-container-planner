"""Coordinate launches and safely hand the shared data directory to a newer app."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class StartupLock:
    def __init__(self, root: Path):
        self.file = (root / 'startup.lock').open('a+b')
        if self.file.seek(0, 2) == 0:
            self.file.write(b'0')
            self.file.flush()
        self.locked = False

    def acquire(self):
        deadline = time.monotonic() + 370
        while True:
            self.file.seek(0)
            try:
                if __import__('sys').platform == 'win32':
                    import msvcrt
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.locked = True
                return
            except OSError:
                if time.monotonic() >= deadline:
                    self.file.close()
                    raise RuntimeError('另一个启动程序仍在准备更新，请稍后重试。')
                time.sleep(.2)

    def release(self):
        if self.file.closed:
            return
        if self.locked:
            self.file.seek(0)
            if __import__('sys').platform == 'win32':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        self.locked = False
        self.file.close()


def version_key(version):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?', str(version))
    if not match:
        raise ValueError('无法识别正在运行的程序版本，请退出旧版后重试。')
    major, minor, patch, suffix = match.groups()
    parts = tuple((1, int(part)) if part.isdigit() else (0, part) for part in (suffix or '').split('.'))
    return int(major), int(minor), int(patch), suffix is None, parts


def coordinate(instance: Path, version: str):
    """Return (reuse_url, freed_port). Only a verified older local instance is stopped."""
    try:
        old = json.loads(instance.read_text(encoding='utf-8'))
        url = old['url']
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('Invalid instance URL')
        identifier = old['id']
    except (OSError, ValueError, KeyError, TypeError):
        return None, None
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with client.open(url + '/api/health', timeout=2) as response:
            health = json.load(response)
    except (OSError, ValueError):
        return None, None
    if not identifier or health.get('instance_id') != identifier:
        return None, None
    if version_key(health.get('version')) >= version_key(version):
        return url, None
    # Existing versions refuse shutdown while the solver is running. Let it finish.
    deadline = time.monotonic() + 330
    while True:
        try:
            request = urllib.request.Request(url + '/api/shutdown', data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
            with client.open(request, timeout=3) as response:
                if not json.load(response).get('ok'):
                    raise RuntimeError('旧版未确认退出，请退出旧版后重试。')
            break
        except urllib.error.HTTPError as error:
            if error.code != 422 or time.monotonic() >= deadline:
                raise RuntimeError('旧版尚未完成排柜，未切换版本。请计算完成后重新打开新版。') from error
            time.sleep(.5)
        except urllib.error.URLError as error:
            raise RuntimeError('无法确认旧版已退出，请稍后重新打开新版。') from error
    # Never start a second writer until the old listener is gone.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with client.open(url + '/api/health', timeout=1) as response:
                current = json.load(response)
                if current.get('instance_id') != identifier:
                    raise RuntimeError('另一个工作台已接管，请重新打开程序。')
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            return None, parsed.port
        time.sleep(.1)
    raise RuntimeError('旧版退出超时，未启动第二个工作台。请稍后重试。')
