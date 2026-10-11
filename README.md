# SW Defect Hub

릴리스 → 브랜치 → 파트 → Perforce CL → 검사 실행 → Finding MD 순서로 조회하는 사내 협업 웹입니다.

초기 구현 버전: **0.1.0**. Ubuntu/Debian + Docker Compose + PostgreSQL을 운영 대상으로 합니다.
외부 CDN, Node 빌드, 인터넷 기반 AI 호출 없이 웹을 실행합니다. 설치 시 이미지와 Python 패키지는 사내 프록시/저장소를 사용할 수 있습니다.

## 포함 기능

- `SVR26B INTEG`, `SVR27A INTEG`, `SVR26B REL COMMON` 등 릴리스와 브랜치를 별도 저장
- 파트: VP, OP, FS, RS, NP, DS, Security
- 웹 수동 업로드와 스킬/자동화용 토큰 인증 업로드 API
- CL 변경 코드의 검사 실행 기록, Finding 0건 정상 완료, 실패·중단, 재실행 이력
- UTF-8 MD 렌더링 및 원본 다운로드, 검색과 페이지 이동
- 실제 결함 / 오탐 / 판단 보류 / 미검토, 수정 진행, 담당자, 댓글, 변경 이력
- 동시 상태 수정 충돌 감지: 다른 사람의 변경을 조용히 덮어쓰지 않음
- 릴리스·브랜치·파트별 통계, 전체 실행/CL별 최신 실행 범위, CSV 다운로드
- 설치, 비밀 설정 생성, 시작/중지, 로그, 업데이트 전 백업, 복원 스크립트

## Ubuntu/Debian 빠른 시작

GitHub에서 소스와 이력을 가져올 수 있습니다.

```bash
git clone https://github.com/JiHuDad/sw-defect-hub.git
cd sw-defect-hub
```

앞서 전달한 ZIP으로 설치하는 경우에는 압축을 푼 소스 폴더를 사용해도 됩니다.
ZIP에 포함된 `repository.bundle`은 당시 초기 Git 이력의 오프라인 복원용입니다.

압축을 풀고 프로젝트 디렉터리에서 실행합니다. Docker 설치에는 sudo 또는 관리자 지원이 필요합니다.

```bash
./scripts/install.sh --port 9999
```

기존 Docker가 있으면 보존하고, 없으면 현재 APT 저장소에서 `docker.io`와 사용 가능한 Compose v2 plugin 패키지를 설치합니다.
사내 저장소에서 Compose 패키지를 제공하지 않으면 원인을 표시하고 중단합니다. 외부 설치 스크립트를 자동 다운로드하지 않습니다.

설치 후 `http://서버IP:9999`로 접속합니다. 초기 데이터는 비어 있습니다. **결과 등록**에서 릴리스·브랜치·파트·CL과 MD를 입력하세요.
MD 없이 정상 완료를 등록하려면 **Finding 없음**을 선택합니다. 실패나 중단은 실행 결과에서 별도로 지정합니다.

Docker를 이미 사용할 수 있다면:

```bash
python3 scripts/configure.py --port 9999
./scripts/manage.sh start
```

프록시·이미지 저장소·접속 권한 설정은 [운영 가이드](docs/OPERATIONS.md)를 확인하세요.

## 자동 업로드

서버 `.env`의 `UPLOAD_TOKEN`을 스캔 장비의 비밀 환경변수 `DEFECT_UPLOAD_TOKEN`으로 전달합니다.
토큰을 Git, MD, 명령행 인자, 스캔 로그에 넣지 마세요. JSON은 아래 클라이언트가 구성합니다.

```bash
export DEFECT_SERVER_URL=http://서버IP:9999
# DEFECT_UPLOAD_TOKEN은 조직의 비밀 설정/환경변수에서 주입

python3 scripts/upload.py \
  --run-id svr26b-integ-vp-cl123456-run001 \
  --release SVR26B --branch INTEG --part VP \
  --cl 123456 --uploader scan-skill \
  examples/finding-001.md
```

Finding 0건:

```bash
python3 scripts/upload.py \
  --run-id svr26b-integ-vp-cl123457-run001 \
  --release SVR26B --branch INTEG --part VP \
  --cl 123457 --uploader scan-skill --no-findings
```

실패:

```bash
python3 scripts/upload.py \
  --run-id svr26b-integ-vp-cl123458-run001 \
  --release SVR26B --branch INTEG --part VP \
  --cl 123458 --uploader scan-skill --status failed --error 'scanner timeout'
```

실행 ID는 검사 시작 시 한 번 생성해 결과와 함께 보관하세요. 전송 재시도에는 같은 ID, 실제 재검사에는 새 ID를 사용합니다.
클라이언트는 통신 오류/5xx에 최대 3회 재시도하며, 결과 파일은 삭제하지 않습니다.
API 규약과 스킬 연결 절차: [API 문서](docs/API.md).

## 개발 실행 및 테스트

운영 데이터와 별도로 Python 3.12 가상환경 및 SQLite를 사용할 수 있습니다.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 9999
```

개발 기본 DB는 프로젝트의 `defects.db`입니다. 자동 업로드를 시험하려면 서버 시작 전에 `UPLOAD_TOKEN`을 설정합니다.
로컬 SQLite는 개발 편의용이고 팀 운영에는 Compose의 PostgreSQL을 사용하세요.

```bash
.venv/bin/pytest -q
node --check app/static/app.js
node --test tests/test_ui.cjs
bash -n scripts/install.sh scripts/manage.sh
```

UI 회귀 테스트는 Node.js 18 이상에서 별도 패키지 설치 없이 실행합니다. 브라우저 클릭 검증을 대체하지는 않습니다.

PostgreSQL 17을 사용하는 별도 임시 컨테이너 환경 테스트:

```bash
./scripts/manage.sh test
```

운영 DB와 다른 프로젝트 이름/임시 DB를 사용하며 테스트 후 제거합니다.

## 운영

```bash
./scripts/manage.sh status
./scripts/manage.sh logs
./scripts/manage.sh backup
./scripts/manage.sh stop
./scripts/manage.sh start
```

MD 원문, 수행 정보, 검토 상태, 의견을 PostgreSQL에 함께 저장합니다. DB 백업 하나로 이 정보들을 일관되게 보관할 수 있습니다.
`.env`와 사내 인증서/프록시 설정은 별도로 안전하게 백업해야 합니다.

## 현재 범위와 향후 확장

- 현재는 로그인 없이 팀이 조회·수정합니다. 작성자 이름은 자기 기입 방식입니다.
- 사내망에서 사용하는 구성입니다. 외부에 공개하기 전 인증과 HTTPS를 구성해야 합니다.
- MD 구조가 미확정이라 제목은 첫 Markdown heading 또는 파일명을 사용합니다. 심각도·함수명 자동 추출은 아직 없습니다.
- 결과 등록은 웹/API로 진행합니다. 지정 폴더 감시와 수집 폴더 매핑 UI는 현재 포함하지 않습니다.
- 재검출 결함 연결, Perforce 직접 접속, AI 스캔 자체 실행은 포함하지 않습니다.
- 릴리스/브랜치는 첫 결과 등록 시 자동 생성됩니다. 빈 릴리스 사전 등록 UI는 없습니다.
- 최초 DB 스키마 생성은 자동입니다. 이후 스키마 변경을 수반하는 버전은 별도 마이그레이션을 추가해야 합니다.

설계 결정과 집계 기준: [설계 문서](docs/DESIGN.md).

실제 수행한 테스트 및 검증 범위: [검증 기록](docs/VALIDATION.md).
