"""Cloud-only legacy server: map official asset URLs to the CI-built package bytes."""
from pathlib import Path
import hashlib
import io
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if __name__ == '__main__':
    archive = Path(sys.argv[1]).resolve()
    version, label = sys.argv[2:4]
    sys.argv = [sys.argv[0], *sys.argv[4:]]
    import container_planner
    container_planner.__version__ = '1.0.0-beta.1'
    from container_planner import updates
    name = f'WoodFlow-{version}-{label}.zip'
    url = f'https://github.com/{updates.REPO}/releases/download/v{version}/'
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    metadata = [{'tag_name': 'v' + version, 'prerelease': '-' in version, 'draft': False, 'body': 'TEST CLOUD UPDATE', 'assets': [
        {'name': name, 'state': 'uploaded', 'size': archive.stat().st_size, 'browser_download_url': url + name, 'digest': 'sha256:' + digest},
        {'name': name + '.sha256.txt', 'state': 'uploaded', 'browser_download_url': url + name + '.sha256.txt'}]}]
    def fixture_url(requested, timeout=30):
        if requested == updates.API_URL: return io.BytesIO(json.dumps(metadata).encode())
        if requested == url + name: return archive.open('rb')
        if requested == url + name + '.sha256.txt': return io.BytesIO((digest + '  ' + name + '\n').encode())
        raise RuntimeError('Unexpected fixture URL')
    updates.open_url = fixture_url
    from container_planner.launcher import main
    main()
