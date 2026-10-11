import importlib.util
from pathlib import Path
import sys


def test_configure_preserves_secrets_and_encodes_proxy(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'scripts/configure.py'
    spec = importlib.util.spec_from_file_location('configure', path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    (tmp_path / '.env.example').write_text('POSTGRES_PASSWORD=\nUPLOAD_TOKEN=\nPIP_INDEX_URL=https://pypi.org/simple\n')
    monkeypatch.setattr(sys, 'argv', ['configure.py', '--port', '9999'])
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.test:3128')
    module.main()
    first = module.read_env(tmp_path / '.env')
    module.main()
    second = module.read_env(tmp_path / '.env')
    assert first['POSTGRES_PASSWORD'] == second['POSTGRES_PASSWORD'] and first['UPLOAD_TOKEN'] == second['UPLOAD_TOKEN']
    assert second['HTTPS_PROXY'] == 'http://proxy.test:3128' and second['PORT'] == '9999'
    assert len(second['POSTGRES_PASSWORD']) == 64
    assert (tmp_path/'.env').stat().st_mode & 0o777 == 0o600
