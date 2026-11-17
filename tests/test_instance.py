import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from container_planner.instance import coordinate, version_key, StartupLock


@pytest.mark.parametrize('older,newer', [('1.1.0-beta.8', '1.1.0-beta.9'), ('1.1.0-beta.9', '1.1.0-beta.10'), ('1.1.0-beta.9', '1.1.0'), ('1.1.0', '1.2.0')])
def test_version_order(older, newer):
    assert version_key(older) < version_key(newer)


def test_verified_upgrade_waits_for_old_job_and_reuses_port(tmp_path):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({'version': '1.1.0-beta.8', 'instance_id': 'test-instance'}).encode())
        def do_POST(self):
            calls.append(self.path)
            self.send_response(422 if len(calls) == 1 else 200); self.end_headers()
            self.wfile.write(b'{"ok":true}')
            if len(calls) > 1:
                threading.Thread(target=server.shutdown, daemon=True).start()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    port = server.server_port
    def serve():
        try: server.serve_forever(poll_interval=.05)
        finally: server.server_close()
    thread = threading.Thread(target=serve, daemon=True); thread.start()
    instance = tmp_path / 'instance.json'
    url = f'http://127.0.0.1:{port}'
    instance.write_text(json.dumps({'url': url, 'id': 'test-instance'}))
    try:
        assert coordinate(instance, '1.1.0-beta.7') == (url, None)
        assert not calls, 'Opening an older binary must not stop the newer service'
        assert coordinate(instance, '1.1.0-beta.8') == (url, None)
        assert coordinate(instance, '1.1.0-beta.9') == (None, port)
        assert calls == ['/api/shutdown', '/api/shutdown']
    finally:
        server.shutdown(); thread.join(timeout=3)


def test_untrusted_instance_and_stale_files(tmp_path):
    instance = tmp_path / 'instance.json'
    assert coordinate(instance, '1.1.0') == (None, None)
    instance.write_text('invalid')
    assert coordinate(instance, '1.1.0') == (None, None)
    instance.write_text(json.dumps({'url': 'https://example.com:443', 'id': 'x'}))
    assert coordinate(instance, '1.1.0') == (None, None)
    lock = StartupLock(tmp_path)
    lock.acquire(); lock.release(); lock.release()
