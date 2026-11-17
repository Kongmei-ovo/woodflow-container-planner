"""Public GitHub updates: verified packages, isolated preflight, explicit restart."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from . import __version__
from .instance import version_key

REPO = 'Kongmei-ovo/woodflow-container-planner'
RELEASES = f'https://github.com/{REPO}/releases'
API_URL = f'https://api.github.com/repos/{REPO}/releases?per_page=50'
MAX_PACKAGE = 400_000_000


def platform_label():
    machine = platform.machine().lower()
    if sys.platform == 'win32' and machine in {'amd64', 'x86_64'}:
        return 'Windows64'
    if sys.platform == 'darwin':
        return 'macOS-arm64' if machine in {'arm64', 'aarch64'} else 'macOS-x64' if machine in {'amd64', 'x86_64'} else None
    return None


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)


def open_url(url, timeout=30):
    request = urllib.request.Request(url, headers={'User-Agent': 'WoodFlow-Updater/' + __version__, 'Accept': 'application/vnd.github+json' if url == API_URL else 'application/octet-stream'})
    return urllib.request.urlopen(request, timeout=timeout)


def download_url(url, version, name):
    expected = f'https://github.com/{REPO}/releases/download/v{version}/{name}'
    if url != expected:
        raise ValueError('更新包来源与官方仓库不一致，已停止更新。')
    return url


def select_release(releases, current, label):
    candidates = []
    # Beta installations follow published beta releases too; stable installs stay stable.
    for release in releases:
        tag = release.get('tag_name', '')
        version = tag[1:] if tag.startswith('v') else ''
        try:
            newer = version_key(version) > version_key(current)
        except ValueError:
            continue
        if release.get('draft') or not newer or ('-' not in current and release.get('prerelease')):
            continue
        assets = {a.get('name'): a for a in release.get('assets', []) if a.get('state') == 'uploaded'}
        name = f'WoodFlow-{version}-{label}.zip'
        asset, checksum = assets.get(name), assets.get(name + '.sha256.txt')
        if not asset or not checksum or not 0 < asset.get('size', 0) <= MAX_PACKAGE:
            continue
        try:
            download_url(asset.get('browser_download_url'), version, name)
            download_url(checksum.get('browser_download_url'), version, name + '.sha256.txt')
        except ValueError:
            continue
        candidates.append({'version': version, 'label': label, 'name': name, 'size': asset['size'], 'url': asset['browser_download_url'], 'checksum_url': checksum['browser_download_url'], 'digest': asset.get('digest'), 'release_url': f'{RELEASES}/tag/v{version}', 'notes': str(release.get('body', ''))[:12000]})
    return max(candidates, key=lambda r: version_key(r['version']), default=None)


def entry_name(entry):
    name = entry.filename
    if not entry.flag_bits & 0x800:
        try:
            name = name.encode('cp437').decode('utf-8')
        except (UnicodeError, LookupError):
            pass
    return name


def validate_archive(archive):
    entries = archive.infolist()
    if len(entries) > 30000 or sum(e.file_size for e in entries) > 1_500_000_000:
        raise ValueError('更新包解压后过大，已停止更新。')
    seen, links = set(), set()
    for entry in entries:
        name = entry_name(entry)
        path = PurePosixPath(name)
        if not name or '\\' in name or path.is_absolute() or any(p in {'..', '.'} or ':' in p for p in path.parts) or name in seen:
            raise ValueError('更新包包含无效路径。')
        seen.add(name)
        if stat.S_ISLNK(entry.external_attr >> 16):
            target = archive.read(entry).decode('utf-8')
            resolved = os.path.normpath(str(path.parent / target))
            if '\\' in target or ':' in target or PurePosixPath(target).is_absolute() or resolved == '..' or resolved.startswith('../'):
                raise ValueError('更新包包含无效链接。')
            links.add(name.rstrip('/'))
    if any(any(str(PurePosixPath(name)).startswith(link + '/') for link in links) for name in seen):
        raise ValueError('更新包链接下存在写入内容。')
    return entries


def command_for(directory, version, label):
    package = directory / f'木序排柜_{version}_{label}'
    if label == 'Windows64':
        command = [package / 'runtime/pythonw.exe', package / 'app/run_planner.py']
    else:
        command = [package / 'WoodFlow.app/Contents/MacOS/WoodFlow']
    if not all(p.is_file() and p.resolve().is_relative_to(directory.resolve()) for p in command):
        raise ValueError('更新包缺少启动程序，请从下载页重新下载。')
    return [str(p.resolve()) for p in command]


def extract_package(path, directory, version, label):
    with ZipFile(path) as archive:
        entries = validate_archive(archive)
        if label == 'Windows64':
            if any(stat.S_ISLNK(e.external_attr >> 16) for e in entries):
                raise ValueError('Windows更新包不能包含链接。')
            archive.extractall(directory)
        else:
            subprocess.run(['/usr/bin/ditto', '-x', '-k', str(path), str(directory)], check=True, timeout=90)
    return command_for(directory, version, label)


def spawn(command, root, no_browser=True, port=0):
    arguments = [*command, '--data-dir', str(root)]
    if no_browser:
        arguments.append('--no-browser')
    if port:
        arguments += ['--port', str(port)]
    kwargs = {'env': {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}, 'cwd': str(Path(command[0]).parent)}
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(arguments, **kwargs)


def managed_command(root, current):
    try:
        active = json.loads((root / 'updates/active.json').read_text(encoding='utf-8'))
        version, label = active['version'], active['label']
        if label != platform_label() or version_key(version) <= version_key(current):
            return None
        return command_for(root / 'updates' / version, version, label)
    except (OSError, KeyError, ValueError, TypeError):
        return None


def activate_managed(root, version):
    label = platform_label()
    try:
        directory = root / 'updates' / version
        command = command_for(directory, version, label)
        if Path(sys.executable).resolve() != Path(command[0]):
            return
        atomic_json(root / 'updates/active.json', {'version': version, 'label': label})
    except (OSError, ValueError, TypeError):
        pass


def preflight(command, version):
    with tempfile.TemporaryDirectory(prefix='woodflow-update-probe-') as directory:
        root = Path(directory)
        process = spawn(command, root)
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url = None
        try:
            for _ in range(150):
                if process.poll() is not None:
                    raise ValueError('新版启动检查失败，仍保留当前版本，请从下载页反馈问题。')
                try:
                    url = json.loads((root / 'instance.json').read_text())['url']
                    with client.open(url + '/api/health', timeout=2) as response:
                        if json.load(response).get('version') == version:
                            return
                except (OSError, ValueError):
                    pass
                time.sleep(.2)
            raise ValueError('新版启动检查超时，仍保留当前版本。')
        finally:
            if url:
                try:
                    client.open(urllib.request.Request(url + '/api/shutdown', data=b'{}', headers={'Content-Type': 'application/json'}), timeout=3).close()
                except OSError:
                    pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate(); process.wait(timeout=10)


class UpdateManager:
    def __init__(self, root, current=__version__):
        self.root, self.current = Path(root), current
        self.lock = threading.RLock()
        self.release = None
        self.checked = 0
        self.state = {'status': 'idle', 'message': '点击检查更新', 'downloaded': 0, 'total': 0, 'release_url': RELEASES, 'platform': platform_label(), 'current_version': current}
        self.command = None

    def status(self):
        with self.lock:
            return dict(self.state)

    def set(self, **values):
        with self.lock:
            self.state.update(values)

    def check(self):
        with self.lock:
            if self.state['status'] in {'checking', 'downloading', 'verifying', 'ready', 'restarting'}:
                return self.status()
            if self.checked and time.monotonic() - self.checked < 60:
                return self.status()
            self.checked = time.monotonic()
            self.set(status='checking', message='正在连接GitHub检查新版本…', error=None)
            threading.Thread(target=self._check, daemon=True).start()
            return self.status()

    def _check(self):
        try:
            with open_url(API_URL, timeout=15) as response:
                releases = json.loads(response.read(2_000_001))
            if not isinstance(releases, list):
                raise ValueError('更新服务返回格式无效。')
            label = platform_label()
            release = select_release(releases, self.current, label) if label else None
            with self.lock:
                self.release = release
                self.set(status='available' if release else 'current', latest_version=release['version'] if release else None, release_url=release['release_url'] if release else RELEASES, notes=release['notes'] if release else '', total=release['size'] if release else 0, message='发现新版本，可下载并准备更新。' if release else '当前已是本更新通道的最新版本。' if label else '此系统不支持自动更新，请前往下载页。')
            if release:
                destination = self.root / 'updates' / release['version']
                try:
                    prepared = json.loads((destination / 'ready.json').read_text(encoding='utf-8'))
                    if prepared['version'] == release['version'] and prepared['name'] == release['name']:
                        self.command = command_for(destination, release['version'], release['label'])
                        self.set(status='ready', message='新版已下载并通过启动检查，保存工作后即可重启更新。')
                except (OSError, ValueError, KeyError):
                    pass
        except Exception as error:
            logging.warning('检查更新失败：%s', error)
            self.set(status='failed', message='无法连接GitHub检查更新，请检查网络后重试，或前往下载页。', error='check')

    def install(self, version):
        with self.lock:
            if self.state['status'] in {'downloading', 'verifying', 'ready'}:
                return self.status()
            if self.state['status'] not in {'available', 'failed'} or not self.release or self.release['version'] != version:
                raise ValueError('请先检查更新，再选择最新版本。')
            self.set(status='downloading', message='正在下载官方更新包…', downloaded=0, error=None)
            threading.Thread(target=self._install, args=(dict(self.release),), daemon=True).start()
            return self.status()

    def _install(self, release):
        workspace = self.root / 'updates'
        try:
            workspace.mkdir(exist_ok=True)
            if shutil.disk_usage(workspace).free < release['size'] * 8:
                raise ValueError('磁盘空间不足，请释放空间后重试。')
            with tempfile.TemporaryDirectory(prefix='staging-', dir=workspace) as temp:
                temp = Path(temp)
                zipped = temp / 'package.zip'
                with open_url(release['checksum_url']) as response:
                    checksum = response.read(1025).decode('utf-8-sig').split()
                if len(checksum) != 2 or not re.fullmatch('[0-9a-fA-F]{64}', checksum[0]) or checksum[1] != release['name']:
                    raise ValueError('更新包校验文件无效。')
                expected = checksum[0].lower()
                if release.get('digest') and release['digest'] != 'sha256:' + expected:
                    raise ValueError('更新包校验信息不一致。')
                digest, size, deadline = hashlib.sha256(), 0, time.monotonic() + 900
                with open_url(release['url']) as response, zipped.open('wb') as output:
                    while chunk := response.read(256 * 1024):
                        size += len(chunk)
                        if size > release['size'] or time.monotonic() > deadline:
                            raise ValueError('下载大小异常或超时，请重试。')
                        output.write(chunk); digest.update(chunk)
                        self.set(downloaded=size)
                if size != release['size'] or digest.hexdigest() != expected:
                    raise ValueError('更新包下载不完整或校验失败，请重试。')
                self.set(status='verifying', message='下载完成，正在解压并检查新版能否启动…')
                unpacked = temp / 'unpacked'; unpacked.mkdir()
                command = extract_package(zipped, unpacked, release['version'], release['label'])
                preflight(command, release['version'])
                destination = workspace / release['version']
                if destination.exists():
                    # A completed installation may be reused, but never overwritten in place.
                    command_for(destination, release['version'], release['label'])
                    raise ValueError('此版本已准备过，请重新打开程序后重试，或从下载页使用该版本。')
                atomic_json(unpacked / 'ready.json', {'version': release['version'], 'name': release['name']})
                os.replace(unpacked, destination)
                self.command = command_for(destination, release['version'], release['label'])
                self.set(status='ready', message='新版已通过启动检查，保存工作后即可重启更新。')
        except Exception as error:
            logging.exception('准备更新失败')
            self.set(status='failed', error='install', message=str(error) if isinstance(error, ValueError) else '下载或准备更新失败，当前版本仍可继续使用。请检查网络或前往下载页。')

    def restart(self, no_browser=False):
        with self.lock:
            if self.state['status'] != 'ready' or not self.command:
                raise ValueError('请先下载并准备更新。')
            self.set(status='restarting', message='正在启动新版并切换工作台，请稍候…')
            try:
                spawn(self.command, self.root, no_browser=no_browser)
            except OSError as error:
                self.set(status='ready', message='无法启动新版，当前版本仍可继续使用，请重试。')
                raise ValueError('无法启动新版，请检查程序权限或前往下载页。') from error
            return self.status()
