from io import BytesIO
import hashlib
import json
import time
from zipfile import ZipFile

import pytest

from container_planner import updates
from test_import_and_api import setup_order


def release(version='1.1.0-beta.11', label='Windows64', data=b'package'):
    name = f'WoodFlow-{version}-{label}.zip'
    url = f'https://github.com/{updates.REPO}/releases/download/v{version}/'
    digest = hashlib.sha256(data).hexdigest()
    return {'tag_name': 'v' + version, 'prerelease': '-' in version, 'draft': False, 'body': 'TEST notes', 'assets': [
        {'name': name, 'state': 'uploaded', 'size': len(data), 'browser_download_url': url + name, 'digest': 'sha256:' + digest},
        {'name': name + '.sha256.txt', 'state': 'uploaded', 'size': 100, 'browser_download_url': url + name + '.sha256.txt'}]}


def settle(manager):
    for _ in range(200):
        if manager.status()['status'] not in {'checking', 'downloading', 'verifying'}:
            return manager.status()
        time.sleep(.01)
    pytest.fail('Update worker did not finish')


def test_choose_complete_official_release_and_channel():
    data = [release('1.1.0-beta.9'), release(), release('1.1.0-beta.10')]
    assert updates.select_release(data, '1.1.0-beta.9', 'Windows64')['version'] == '1.1.0-beta.11'
    assert updates.select_release(data, '1.0.0', 'Windows64') is None
    assert updates.select_release(data, '1.1.0-beta.9', 'macOS-arm64') is None
    bad = release('9.0.0')
    bad['assets'][0]['browser_download_url'] = 'https://example.com/program.exe'
    assert updates.select_release([bad], '1.0.0', 'Windows64') is None
    bad = release('9.0.0'); bad['assets'].pop()
    assert updates.select_release([bad], '1.0.0', 'Windows64') is None
    data = [release('2.0.0'), release('3.0.0')]; data[-1]['draft'] = True
    assert updates.select_release(data, '1.0.0', 'Windows64')['version'] == '2.0.0'


@pytest.mark.parametrize('member', ['../outside.txt', '/absolute.txt', 'C:/outside.txt', 'folder/../../outside.txt', 'folder\\outside.txt'])
def test_reject_unsafe_archives(member):
    stream = BytesIO()
    with ZipFile(stream, 'w') as zipped:
        zipped.writestr(member, 'invalid')
    with ZipFile(BytesIO(stream.getvalue())) as zipped, pytest.raises(ValueError):
        updates.validate_archive(zipped)


@pytest.mark.parametrize('corrupt', [False, True])
def test_download_hash_preflight_and_managed_pointer(monkeypatch, tmp_path, corrupt):
    monkeypatch.setattr(updates, 'platform_label', lambda: 'Windows64')
    version = '1.1.0-beta.11'
    prefix = f'木序排柜_{version}_Windows64'
    stream = BytesIO()
    with ZipFile(stream, 'w') as zipped:
        zipped.writestr(prefix + '/runtime/pythonw.exe', b'TEST binary')
        zipped.writestr(prefix + '/app/run_planner.py', b'TEST script')
    data = stream.getvalue()
    metadata = release(data=data)
    selected = updates.select_release([metadata], '1.1.0-beta.10', 'Windows64')
    def open_url(url, timeout=30):
        if url == updates.API_URL: return BytesIO(json.dumps([metadata]).encode())
        if url == selected['checksum_url']: return BytesIO((hashlib.sha256(data).hexdigest() + '  ' + selected['name'] + '\n').encode())
        if url == selected['url']: return BytesIO(b'x' * len(data) if corrupt else data)
        pytest.fail('Unexpected URL')
    monkeypatch.setattr(updates, 'open_url', open_url)
    probes = []
    monkeypatch.setattr(updates, 'preflight', lambda command, version: probes.append((command, version)))
    manager = updates.UpdateManager(tmp_path, current='1.1.0-beta.10')
    manager.check(); assert settle(manager)['status'] == 'available'
    manager.install(version); result = settle(manager)
    assert result['status'] == ('failed' if corrupt else 'ready'), result
    assert not (tmp_path / 'updates/active.json').exists(), 'Preparing must not activate an update'
    assert len(probes) == (0 if corrupt else 1)
    if not corrupt:
        manager2 = updates.UpdateManager(tmp_path, current='1.1.0-beta.10')
        manager2.check(); assert settle(manager2)['status'] == 'ready', 'Prepared update must survive an application restart'
        updates.atomic_json(tmp_path / 'updates/active.json', {'version': version, 'label': 'Windows64'})
        assert updates.managed_command(tmp_path, '1.1.0-beta.10')[0].endswith('pythonw.exe')
        assert updates.managed_command(tmp_path, version) is None


def test_offline_check_is_a_nonfatal_status(monkeypatch, tmp_path):
    def fail(*args, **kwargs): raise OSError('offline')
    monkeypatch.setattr(updates, 'open_url', fail)
    manager = updates.UpdateManager(tmp_path)
    manager.check(); assert settle(manager)['status'] == 'failed'
    assert not (tmp_path / 'updates/active.json').exists()


def test_restart_requires_prepared_package_and_keeps_automatic_backup(client, monkeypatch):
    identifier = setup_order(client)
    assert client.post('/api/updates/install', json={'version': '9.0.0', 'url': 'https://example.com/'}).status_code == 422
    assert client.post('/api/updates/restart').status_code == 422
    manager = client.app.state.updates
    manager.set(status='ready')
    manager.command = ['TEST']
    class Running:
        def is_alive(self): return True
    client.app.state.processes['test'] = Running()
    assert client.post('/api/updates/restart').status_code == 422
    client.app.state.processes.clear()
    launched = []
    monkeypatch.setattr(updates, 'spawn', lambda *args, **kwargs: launched.append(args))
    response = client.post('/api/updates/restart')
    assert response.status_code == 200, response.text
    assert len(launched) == 1
    backup = client.get('/api/updates/backup')
    assert backup.status_code == 200
    with ZipFile(BytesIO(backup.content)) as archive:
        assert 'planner.sqlite3' in archive.namelist()
        assert any(p.startswith('originals/') for p in archive.namelist())
        assert not any(p.startswith('updates/') for p in archive.namelist())
    assert client.get('/api/projects/' + identifier).status_code == 200
