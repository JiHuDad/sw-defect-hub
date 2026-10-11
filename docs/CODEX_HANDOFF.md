# Codex 작업 인계 — SW Defect Hub

## 시작 위치
- 2026-10-11 Mac 후속 검증 완료: 아래 기록 및 docs/VALIDATION.md 참조.
- 사용자 Mac 저장소: /Users/fall/dev/sw-defect-hub
- GitHub: https://github.com/JiHuDad/sw-defect-hub
- 구현 반영 commit: 3948ffce3d0c7b985fefba0a7e5cef9f416a0133
- 이 문서는 Chat/Work에서 진행한 설계와 개발을 로컬 Codex 작업으로 이어가기 위한 인계 자료다.
- 이전 작업 환경은 Mac 경로에 접근하지 못했으며 GitHub API로 main에 반영했다. Mac checkout 동기화 여부는 확인하지 않았다.

## 사용자와 확정한 요구사항
- 사내 Ubuntu/Debian 서버 운영. sudo 또는 관리자 지원 가능.
- 인터넷은 사내 프록시/저장소를 통해 접근. 설치·설정·실행·백업 자동화.
- 릴리스와 브랜치를 별도 관리: SVR26B INTEG, SVR27A INTEG, SVR26B REL COMMON.
- 파트: VP, OP, FS, RS, NP, DS, Security.
- 릴리스 → 브랜치 → 파트 → CL → 검사 실행 → Finding MD 순서로 조회.
- 검사 범위는 해당 Perforce CL의 변경 코드 중심.
- MD 하나에 Finding 하나. 실제 MD 샘플은 아직 없다.
- Finding 0건 정상 완료, 실패·중단, 동일 CL 재실행 이력을 모두 보관.
- 자동 업로드(스캔 스킬)와 웹 수동 업로드를 모두 지원. JSON은 자동 클라이언트가 구성.
- 웹 로그인 없이 팀원 모두 검토·상태 변경. 작성자 이름은 자기 기입.
- 결함 판단(실제 결함/오탐/보류/미검토), 수정 진행, 담당자, 댓글, 변경 이력.
- 버전·파트별 건수와 실제 결함/오탐 비율, CSV.
- 재검출 결함 연결은 초기 범위 제외.
- 폴더 감시는 현재 구현에 포함하지 않음. 최신 등록 방식 결정은 웹/API 업로드.

## 현재 구현
FastAPI + SQLAlchemy + PostgreSQL + Nginx + Docker Compose.
프런트엔드는 CDN 없는 HTML/CSS/JavaScript. 개발용 SQLite 지원.

- app/main.py: 조회·업로드·검토·통계 API, MD 렌더링, 같은 origin 확인.
- app/models.py: Run, Finding, Event.
- app/static/: 탐색, 수동 업로드, 원본 열람, 검토·댓글·통계 화면.
- scripts/upload.py: 표준 라이브러리 자동 업로드 클라이언트. 환경변수로 서버/토큰 전달.
- scripts/install.sh, configure.py, configure-daemon.py, manage.sh: 설치·설정·운영.
- compose.test.yaml: 운영 DB와 분리한 PostgreSQL 17 테스트 환경.
- docs/DESIGN.md, API.md, OPERATIONS.md, VALIDATION.md: 상세 설계와 제한.

## 현재 화면 구성

- 왼쪽 고정 메뉴: 검사 결과 / 통계 / 결과 등록.
- 파트 선택은 실행/Finding 유무와 관계없이 VP, OP, FS, RS, NP, DS, Security 전체를 고정 순서로 표시하며 미등록 파트는 0건으로 표시.
- 검사 결과 시작 화면은 PKG 버전 카드. 버전 → 브랜치 → 파트 → CL → 실행 → Finding으로 탐색.
- 통계는 별도 메뉴에서 조회하며 선택 중인 버전/브랜치/파트를 이어받음. PKG 버전은 기존 release 필드의 화면 명칭이며 DB/API는 유지.
- 단계별 범위·통계 모드 URL 보존. 기존 Run/Finding 직접 링크 지원.

## 중요한 동작
- 같은 execution_id와 같은 내용 재전송은 중복 생성하지 않음.
- 같은 execution_id에 다른 내용은 409. 실제 재검사는 새 ID.
- MD 원문과 메타데이터는 불변. 재검사에 이전 검토 상태를 자동 복사하지 않음.
- revision으로 동시 상태 수정 충돌 감지.
- 정상 완료 Finding만 기본 결함 통계에 포함. 실패 시 부분 결과는 보관하되 제외.
- 오탐률 = 오탐/(실제 결함+오탐). 미검토·보류는 분모에서 제외.
- 전체 실행과 CL별 최신 등록 실행 집계 선택. 둘 다 이력은 보존.
- Finding 0건 정상 완료는 no_findings=true로 명시.
- 원본 MD는 UTF-8 텍스트로 DB에 저장. BOM/CRLF 다운로드 보존.
- MD당 5 MiB, 실행당 100개/합계 50 MiB.
- 운영 DB/앱 포트는 외부 미공개. 기본 웹 포트 9999.

## 검증 사실과 남은 작업
- 사용자 Mac Python 3.12.14/SQLite: 테스트 27개 통과 (실제 HTTP 클라이언트 포함).
- Node UI 회귀 테스트 6개 통과. 수동 0건/MD/중단 등록, MD 렌더링, 상태·담당자·댓글·이력 저장, 새로고침 보존, 전체/최신 통계를 실제 브라우저에서 확인.
- 상세 화면의 탐색 갱신, 업로드 옵션 모순 방지, 요약 중단 건수 표시를 수정.
- 실제 로컬 HTTP 서버와 업로드 클라이언트 통신 검증 완료.
- JS/shell/Python syntax와 Compose YAML 파싱 완료.
- 이 Mac에는 Docker가 없음. Docker build/start, 실제 PostgreSQL 통합 테스트, pg_dump/restore 왕복은 미완료. 모바일 화면과 브라우저 다운로드 저장도 미검증.
- PostgreSQL 테스트 구성은 제공했지만 실행 통과로 보고하면 안 됨.
- 실제 Linux 테스트 서버는 아직 준비되지 않았다. 사용자가 준비되면 알려주기로 했다.
- 회사 프록시/이미지/CA/방화벽 값과 실제 MD 양식도 미제공.

## Codex에서 다음에 할 일
1. git status, 현재 branch, origin을 먼저 확인. 기존 사용자 변경을 보존.
2. 원격을 fetch하고 변경을 확인. 깨끗한 checkout에서만 적절한 fast-forward로 동기화.
3. 문서와 코드를 검토하고 현재 Mac 환경의 Python/Docker 도구를 확인.
4. 가능하면 로컬 테스트와 실제 브라우저 동작을 검증하고 관찰된 문제를 수정.
5. Docker가 가능하면 분리된 PostgreSQL 환경으로 scripts/manage.sh test 실행.
6. Linux 서버가 제공되기 전에는 사내 서버에 배포한 것으로 보고하지 않음.
7. 수정은 실제 확인한 동작과 테스트 근거를 기록하고 commit/push. 원격 main은 사용자에게 반영 권한을 받은 상태.
8. 실제 스캔 스킬 소스가 제공되면 업로드 단계를 연결. 그전에는 클라이언트/규약 제공 상태로 명시.

## 사용자 선호
웹 개발 경험이 적으므로 동작과 사용 흐름을 쉽게 설명할 것.
설계는 이미 위와 같이 정리했으므로 같은 요구사항 질문을 반복하지 말 것.
현재 결과를 재검토하고 검증하는 것부터 시작하며 대규모 재작성은 근거 없이 하지 말 것.
