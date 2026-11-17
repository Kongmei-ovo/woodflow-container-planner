import pytest

from test_import_and_api import setup_order, wait_job


def test_order_edit_delete_restore_keeps_snapshots(client):
    identifier = setup_order(client)
    original = client.get('/api/projects/' + identifier).json()
    job = client.post(f'/api/projects/{identifier}/solve', json={'revision': original['revision'], 'seconds': 1}).json()
    plan_id = wait_job(client, job['id'])['plan_id']
    plan = client.get('/api/plans/' + plan_id).json()
    exported = client.post(f'/api/plans/{plan_id}/export').json()
    edited = client.patch('/api/projects/' + identifier, json={'revision': original['revision'], 'name': 'TEST renamed', 'customer': 'TEST customer', 'notes': 'TEST notes'})
    assert edited.status_code == 200, edited.text
    assert client.patch('/api/projects/' + identifier, json={'revision': original['revision'], 'name': 'stale'}).status_code == 409
    assert client.patch('/api/projects/' + identifier, json={'revision': edited.json()['revision'], 'name': ' '}).status_code == 422
    assert client.request('DELETE', '/api/projects/' + identifier, json={}).status_code == 422
    # TestClient's delete helper does not accept JSON on every httpx version.
    deleted = client.request('DELETE', '/api/projects/' + identifier, json={'revision': edited.json()['revision']})
    assert deleted.status_code == 200, deleted.text
    state = client.get('/api/bootstrap').json()
    assert not state['projects'] and not state['plans']
    assert state['deleted_projects'][0]['id'] == identifier
    assert client.post(f'/api/projects/{identifier}/solve', json={'revision': deleted.json()['revision']}).status_code == 422
    assert client.get('/api/plans/' + plan_id).json() == plan
    assert client.get('/api/exports/' + exported['id']).content.startswith(b'PK')
    restored = client.post(f'/api/projects/{identifier}/restore', json={'revision': deleted.json()['revision']})
    assert restored.status_code == 200
    state = client.get('/api/bootstrap').json()
    assert not state['deleted_projects']
    p = state['projects'][0]
    assert p['name'] == 'TEST renamed' and p['customer'] == 'TEST customer'
    assert p['factories'] == ['利泰'] and p['warehouses'] == ['DCSYD']
    assert state['plans'][0]['id'] == plan_id
    actions = [a['action'] for a in client.get('/api/history').json()]
    assert {'修改订单信息', '订单移入回收站', '恢复订单'} <= set(actions)


def test_cannot_delete_order_while_solver_running(client):
    identifier = setup_order(client)
    class Running:
        def is_alive(self): return True
    client.app.state.store.put('job', {'project_id': identifier, 'status': 'running'}, 'test-running')
    client.app.state.processes['test-running'] = Running()
    p = client.get('/api/projects/' + identifier).json()
    assert client.request('DELETE', '/api/projects/' + identifier, json={'revision': p['revision']}).status_code == 422
    assert client.get('/api/bootstrap').json()['projects']
