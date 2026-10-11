# 설치·운영

## 사내 프록시와 저장소

설치 경로는 세 부분입니다. 각각의 프록시가 별도로 필요할 수 있습니다.

| 대상 | 설정 위치 |
|---|---|
| Ubuntu/Debian APT 패키지 | 회사가 관리하는 /etc/apt/sources.list.d, APT proxy 설정 |
| Docker 이미지 pull | Docker daemon proxy 또는 사내 미러 |
| Python 패키지 build | .env의 PIP_INDEX_URL, HTTP_PROXY, HTTPS_PROXY, NO_PROXY |

기존 사내 APT 설정은 설치 스크립트가 덮어쓰지 않습니다. 관리자에게 docker.io와 Compose v2 plugin 패키지가 제공되는지 확인하세요.
Docker CE를 회사 표준으로 설치한 서버는 그대로 사용합니다.

`.env.example`을 `.env`로 복사해 주소들을 수정하거나 환경변수를 설정한 뒤 `scripts/configure.py`를 실행하세요.
이 스크립트는 비밀번호·업로드 토큰을 자동 생성하고 기존 값을 유지합니다.
PIP 저장소 설정은 `.pip.conf`에 생성되며 Docker build secret으로 사용합니다.

```bash
export HTTP_PROXY=http://사내프록시:포트
export HTTPS_PROXY=http://사내프록시:포트
export NO_PROXY=localhost,127.0.0.1,db,app,web,사내서버도메인
export PIP_INDEX_URL=https://사내패키지서버/simple
python3 scripts/configure.py --port 9999
```

Docker daemon이 프록시를 필요로 한다면, 전용 서버에서 다음 명령으로 설정할 수 있습니다.
**Docker 서비스를 재시작하므로 다른 컨테이너가 있는 서버는 작업 시간을 조정하세요.**

```bash
sudo -E python3 scripts/configure-daemon.py
# 미러가 필요한 경우:
sudo -E python3 scripts/configure-daemon.py --registry-mirror https://사내미러
```

기존 daemon.json의 다른 키는 보존하고 미러를 추가합니다. 수정 전 사본을 남깁니다.
회사 표준 프록시 drop-in이 있으면 충돌 여부를 관리자와 확인하세요.

사내 이미지 저장소를 직접 사용하는 경우 `.env`의 다음 값을 변경합니다.

```text
PYTHON_IMAGE=사내레지스트리/python:3.12-slim
POSTGRES_IMAGE=사내레지스트리/postgres:17-alpine
NGINX_IMAGE=사내레지스트리/nginx:1.28-alpine
```

레지스트리 로그인은 조직 표준 `docker login`/credential helper로 수행합니다. 인증서를 검증하는 설정을 유지합니다.
사내 CA가 필요하면 Docker 호스트 trust와 빌드 이미지의 CA trust를 각각 구성해야 합니다.
이 주소·CA·자격증명은 제공되지 않았으므로 실제 값은 운영 서버에서 설정해야 합니다.
인터넷 프록시의 비밀번호에 $, #, 공백 등 특수문자가 있다면 URL 인코딩하세요.

## 접속

기본 BIND_ADDRESS=0.0.0.0, PORT=9999. 서버의 실제 IP로 접속합니다.
APT/systemd/Docker 설치 권한과 Docker socket 접근 권한이 필요합니다.
sudo 설치 후 파일 소유권 때문에 일반 사용자 실행이 제한되면 관리자가 프로젝트 소유권을 운영 계정으로 조정하세요.

방화벽은 회사 정책에 맞춰 9999 포트를 팀의 네트워크에 허용합니다. 스크립트가 방화벽을 자동 개방하지 않습니다.
DB와 앱 포트는 외부로 노출하지 않습니다.
서버가 회사 HTTPS reverse proxy 뒤에 있다면 `PUBLIC_URL=https://실제주소`로 지정하고 해당 proxy에서 TLS를 종료하세요.
PUBLIC_URL은 browser Origin 검증에 사용합니다. prefix 없는 루트 경로로 서비스합니다.
업로드 토큰을 전송하는 실제 운영 경로에는 회사 HTTPS를 사용하는 것을 권장합니다.

## 백업과 복원

```bash
./scripts/manage.sh backup
```

PostgreSQL custom dump를 `backups/`에 권한을 제한해 저장합니다. 데이터베이스 안에 원본 MD도 들어 있으므로 함께 백업됩니다.
백업 파일을 다른 서버/회사 백업 저장소에도 보관하세요. 자동 백업 스케줄은 아직 설정하지 않습니다.
`.env`와 .pip.conf, 사내 인증서는 DB dump에 포함되지 않습니다. 별도의 비밀 보관 절차로 백업합니다.

복원은 현재 데이터베이스를 교체합니다. 대상 dump를 먼저 확인하고 실행하세요.

```bash
./scripts/manage.sh restore --replace-database backups/defects-날짜.dump
```

복원 중 app/web을 중지하고 DB 복원은 단일 트랜잭션으로 수행합니다. 성공/실패 후 서비스를 다시 시작합니다.
복원 후 `/healthz` 및 결과/원본 MD/검토 이력을 확인하세요.
새 서버에 복원할 때도 동일 버전 프로젝트를 시작해 db가 실행되는 상태에서 수행합니다.

## 업데이트

검토한 새 Git commit으로 이동한 뒤:

```bash
./scripts/manage.sh update
```

현재 DB를 백업하고 앱을 다시 build/start합니다. 임의의 원격 브랜치를 자동 pull하지 않습니다.
0.1.0은 최초 테이블 자동 생성만 수행합니다. 이후 스키마 변경 버전에서는 제공되는 migration 명령을 확인해야 합니다.
일반 stop/start/update는 DB volume을 삭제하지 않습니다. `docker compose down -v`는 데이터를 삭제하므로 일상 운영에 사용하지 마세요.

## 장애 확인

```bash
./scripts/manage.sh status
./scripts/manage.sh logs
```

- 이미지 pull 실패: daemon proxy, registry 로그인/CA/미러 확인
- pip 실패: 사내 index-url에서 requirements의 고정 버전 제공 여부 확인
- DB unhealthy: DB 로그와 디스크 공간 확인
- 웹 접속 실패: 서버 IP/PORT/방화벽 확인
- 403 상태 변경: PUBLIC_URL/Origin 및 proxy의 Host 전달 확인
- 409 업로드: 동일 실행 ID에 메타데이터나 파일 내용이 달라졌는지 확인
- 413 업로드: MD당 5 MiB, 합계 50 MiB, 최대 100개 제한 확인
- 실패 후 수동 등록: 같은 원본 실행 ID를 유지하면 자동 재전송과 중복을 방지할 수 있음

## 실행 이력과 저장 비용

모든 재검사 이력을 보관합니다. 업로드 파일은 SHA-256을 기록하지만 실행 사이에서 자동 중복 제거하지 않습니다.
오래된 이력을 삭제하는 API는 현재 없습니다. 실제 규모와 보관 정책을 확인한 뒤 별도 retention 기능을 추가할 수 있습니다.
통계의 전체 실행/CL별 최신 실행 기준은 [설계 문서](DESIGN.md)를 참고하세요.
