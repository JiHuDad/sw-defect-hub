#!/usr/bin/env python3
"""Create private configuration; preserve existing settings and never print secrets."""
import argparse
import os
from pathlib import Path
import re
import secrets

ROOT = Path(__file__).resolve().parents[1]


def read_env(path):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values[key.strip()] = value
    return values


def main():
    parser = argparse.ArgumentParser(description='SW Defect Hub 초기 설정')
    parser.add_argument('--port', type=int)
    parser.add_argument('--bind')
    parser.add_argument('--public-url')
    args = parser.parse_args()
    values = read_env(ROOT / '.env.example') | read_env(ROOT / '.env')
    if args.port is not None:
        if not 1 <= args.port <= 65535:
            parser.error('포트는 1~65535여야 합니다.')
        values['PORT'] = str(args.port)
    if args.bind:
        values['BIND_ADDRESS'] = args.bind
    if args.public_url:
        values['PUBLIC_URL'] = args.public_url.rstrip('/')
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'PIP_INDEX_URL', 'PYTHON_IMAGE', 'POSTGRES_IMAGE', 'NGINX_IMAGE']:
        if key in os.environ:
            values[key] = os.environ[key]
    for key in ['POSTGRES_PASSWORD', 'UPLOAD_TOKEN']:
        if not values.get(key):
            values[key] = secrets.token_hex(32)
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', values['POSTGRES_PASSWORD']):
        parser.error('DB 비밀번호는 URL에 안전한 영문·숫자·_·- 16~128자여야 합니다.')
    for value in values.values():
        if any(c in value for c in '\r\n\x00'):
            parser.error('설정에 줄바꿈을 사용할 수 없습니다.')
    path = ROOT / '.env'
    # Single quoting prevents Compose interpolation of dollar signs in proxy credentials.
    if any("'" in value for value in values.values()):
        parser.error('설정의 작은따옴표는 URL 인코딩하세요.')
    path.write_text('\n'.join(f"{key}='{value}'" for key, value in values.items()) + '\n')
    path.chmod(0o600)
    pip_conf = ROOT / '.pip.conf'
    pip_conf.write_text('[global]\nindex-url = ' + values['PIP_INDEX_URL'] + '\n')
    pip_conf.chmod(0o600)
    print('설정 완료: .env 및 .pip.conf (기존 값 유지, 비밀 값 출력 안 함)')


if __name__ == '__main__':
    main()
