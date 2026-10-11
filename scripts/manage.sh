#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if docker compose version >/dev/null 2>&1; then
  compose=(docker compose)
else
  printf '%s\n' 'Docker Compose plugin이 필요합니다. scripts/install.sh를 실행하세요.' >&2
  exit 1
fi
action="${1:-status}"
case "$action" in
  start) "${compose[@]}" up -d --build --wait ;;
  stop) "${compose[@]}" stop ;;
  status) "${compose[@]}" ps ;;
  logs) "${compose[@]}" logs --tail=100 -f ;;
  test)
    trap '"${compose[@]}" -f compose.test.yaml down' EXIT
    "${compose[@]}" -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
    ;;
  backup)
    mkdir -p backups
    chmod 700 backups
    target="backups/defects-$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}.dump"
    umask 077
    "${compose[@]}" exec -T db pg_dump -U defects -d defects -Fc > "$target.tmp"
    mv "$target.tmp" "$target"
    printf '백업 완료: %s\n' "$target"
    ;;
  restore)
    if [[ "${2:-}" != '--replace-database' || ! -f "${3:-}" ]]; then
      printf '%s\n' '사용법: scripts/manage.sh restore --replace-database backups/파일.dump (현재 DB를 교체합니다)' >&2
      exit 1
    fi
    "${compose[@]}" exec -T db pg_restore --list < "$3" >/dev/null
    "${compose[@]}" stop web app
    trap '"${compose[@]}" start app web' EXIT
    "${compose[@]}" exec -T db pg_restore -U defects -d defects --clean --if-exists --exit-on-error --single-transaction < "$3"
    ;;
  update)
    # Repository fetching is separate so the operator selects a reviewed commit first.
    "$0" backup
    "${compose[@]}" build app
    "${compose[@]}" up -d --wait
    ;;
  *) printf '%s\n' '사용법: scripts/manage.sh start|stop|status|logs|test|backup|restore|update' >&2; exit 1 ;;
esac
