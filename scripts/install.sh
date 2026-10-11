#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -r /etc/os-release ]]; then printf '%s\n' 'Ubuntu/Debian 서버에서 실행하세요.' >&2; exit 1; fi
source /etc/os-release
if [[ "$ID" != ubuntu && "$ID" != debian ]]; then printf '%s\n' '이 설치 스크립트는 Ubuntu/Debian 대상입니다.' >&2; exit 1; fi
if (( EUID == 0 )); then root=(); else root=(sudo); fi
if ! command -v docker >/dev/null 2>&1; then
  "${root[@]}" apt-get update
  "${root[@]}" apt-get install -y docker.io python3 ca-certificates
fi
if ! docker compose version >/dev/null 2>&1; then
  "${root[@]}" apt-get update
  if apt-cache show docker-compose-v2 >/dev/null 2>&1; then
    "${root[@]}" apt-get install -y docker-compose-v2
  elif apt-cache show docker-compose-plugin >/dev/null 2>&1; then
    "${root[@]}" apt-get install -y docker-compose-plugin
  else
    printf '%s\n' '사내 APT 저장소에 Compose v2 plugin 패키지가 필요합니다. docs/OPERATIONS.md를 확인하세요.' >&2
    exit 1
  fi
fi
"${root[@]}" systemctl enable --now docker
if ! command -v python3 >/dev/null 2>&1; then "${root[@]}" apt-get install -y python3; fi
python3 scripts/configure.py "$@"
if ! docker info >/dev/null 2>&1; then
  printf '%s\n' 'Docker 접근 권한이 없습니다. 관리자에게 docker 그룹 권한을 받거나 sudo -E로 설치를 실행하세요.' >&2
  exit 1
fi
scripts/manage.sh start
printf '%s\n' '설치 완료. http://서버주소:설정포트 에 접속하세요. 기본 포트: 9999'
