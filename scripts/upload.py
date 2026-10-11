#!/usr/bin/env python3
"""Standard-library client for scan skills. Reuse --run-id for transport retries."""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import uuid


def main():
    parser = argparse.ArgumentParser(description='완료된 CL 검사 결과 자동 업로드')
    parser.add_argument('--server', default=os.getenv('DEFECT_SERVER_URL'))
    parser.add_argument('--run-id', required=True, help='검사 시작 시 생성한 ID. 업로드 재시도 시 같은 ID 유지')
    for name in ['release', 'branch', 'part', 'cl', 'uploader']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--status', choices=['completed', 'failed', 'cancelled'], default='completed')
    parser.add_argument('--no-findings', action='store_true')
    parser.add_argument('--tool', default='')
    parser.add_argument('--model', default='')
    parser.add_argument('--notes', default='')
    parser.add_argument('--error', default='')
    parser.add_argument('--started-at')
    parser.add_argument('--finished-at')
    parser.add_argument('files', nargs='*', type=Path)
    args = parser.parse_args()
    token = os.getenv('DEFECT_UPLOAD_TOKEN', '')
    if not args.server or not token:
        parser.error('DEFECT_SERVER_URL 및 DEFECT_UPLOAD_TOKEN 환경변수를 설정하세요.')
    parsed = urlsplit(args.server)
    if parsed.scheme not in ['http', 'https'] or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        parser.error('서버 주소는 http(s) 주소여야 하며 인증정보·query·fragment를 포함하지 않습니다.')
    if len(args.files) > 100:
        parser.error('한 실행에 최대 100개 파일을 등록할 수 있습니다.')
    if args.status == 'completed' and not args.files and not args.no_findings:
        parser.error('파일이 없는 정상 완료에는 --no-findings가 필요합니다.')
    metadata = {k: getattr(args, k) for k in ['release', 'branch', 'part', 'cl', 'uploader', 'status',
                'no_findings', 'tool', 'model', 'notes', 'error', 'started_at', 'finished_at']}
    metadata['execution_id'] = args.run_id
    boundary = 'DefectHub-' + uuid.uuid4().hex
    body = bytearray()
    def field(header, payload):
        body.extend(f'--{boundary}\r\n{header}\r\n\r\n'.encode());body.extend(payload);body.extend(b'\r\n')
    field('Content-Disposition: form-data; name="metadata"', json.dumps(metadata, ensure_ascii=False).encode())
    size = 0
    for path in args.files:
        if not path.is_file() or path.suffix.lower() != '.md' or path.stat().st_size > 5*1024*1024:
            parser.error(f'MD 파일 또는 크기를 확인하세요: {path}')
        if any(c in path.name for c in '"\r\n\\'):
            parser.error('파일명에 따옴표·줄바꿈·역슬래시를 사용할 수 없습니다.')
        content = path.read_bytes();size += len(content)
        if size > 50*1024*1024:
            parser.error('합계 50 MiB를 초과했습니다.')
        field(f'Content-Disposition: form-data; name="files"; filename="{path.name}"\r\nContent-Type: text/markdown', content)
    body.extend(f'--{boundary}--\r\n'.encode())
    request = Request(args.server.rstrip('/') + '/api/runs', data=bytes(body), headers={
        'Authorization': 'Bearer ' + token, 'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST')
    for attempt in range(3):
        try:
            with urlopen(request, timeout=120) as response:
                result = json.load(response)
                result['url'] = args.server.rstrip('/') + result['url']
                print(json.dumps(result, ensure_ascii=False))
                return
        except HTTPError as exc:
            if exc.code < 500 or attempt == 2:
                parser.exit(1, f'업로드 실패 HTTP {exc.code}: {exc.read(4096).decode(errors="replace")}\n')
        except (URLError, TimeoutError):
            if attempt == 2:
                parser.exit(1, '서버 접속 실패. 결과 파일과 실행 ID를 보관하고 재시도하세요.\n')
        time.sleep(2 ** attempt)


if __name__ == '__main__':
    main()
