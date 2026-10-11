#!/usr/bin/env python3
"""Optional Docker daemon proxy setup. Reads environment; does not print proxy credentials."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description='Docker 이미지 다운로드용 프록시/미러 설정 (root)')
    parser.add_argument('--registry-mirror', help='선택: Docker Hub 미러 URL')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('sudo -E python3 scripts/configure-daemon.py 로 실행하세요.')
    values = {k: os.getenv(k, '') for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']}
    if not any(values.values()) and not args.registry_mirror:
        parser.error('프록시 환경변수 또는 --registry-mirror가 필요합니다.')
    if any('\n' in v or '\r' in v or '\x00' in v for v in values.values()):
        parser.error('설정에 제어문자를 사용할 수 없습니다.')
    if any(values.values()):
        directory = Path('/etc/systemd/system/docker.service.d')
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / 'sw-defect-proxy.conf'
        def escape(value):
            return value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
        target.write_text('[Service]\n' + '\n'.join(f'Environment="{k}={escape(v)}"' for k,v in values.items()) + '\n')
        target.chmod(0o600)
    if args.registry_mirror:
        if not args.registry_mirror.startswith(('http://', 'https://')):
            parser.error('미러 URL은 http(s) 주소여야 합니다.')
        target = Path('/etc/docker/daemon.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        config = json.loads(target.read_text()) if target.exists() else {}
        mirrors = config.setdefault('registry-mirrors', [])
        if args.registry_mirror not in mirrors:
            mirrors.append(args.registry_mirror)
        if target.exists():
            target.with_suffix('.json.sw-defect-backup').write_bytes(target.read_bytes())
        target.write_text(json.dumps(config, indent=2) + '\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'restart', 'docker'], check=True)
    print('Docker daemon 설정 완료. Docker 서비스가 재시작되었습니다.')


if __name__ == '__main__':
    main()
