# 검증 기록

검증일: 2026-10-11. 실행 환경: Python 3.12, SQLite, 로컬 HTTP 서버.

## 완료

- pytest 통합 테스트 **27개 통과**
- 자동/수동 multipart 업로드, 정상 완료 Finding 0건, 실패/중단 검증
- 같은 실행 ID 재전송 및 다른 내용 충돌, 실제 재검사 실행 분리
- 잘못된 분류/시각/파일명/UTF-8/빈 파일/크기/중복 파일명 거부와 원자적 등록
- 한글 제목, UTF-8 BOM/CRLF 원본 바이트 보존, HTML/위험 링크/외부 이미지 처리
- 상태 동시 수정 revision 충돌과 작성자·댓글·변경 전후 값 이력
- 정상 완료/실패 집계 분리, 오탐률·검토율 분모, CL별 최신 실행, 필터/페이지, CSV 수식 방지
- 실제 Uvicorn HTTP 서버와 표준 라이브러리 업로드 클라이언트 통신: 한글 MD, 재전송, 409, 0건, 실패
- 초기 설정 재실행 시 비밀번호/토큰 유지 및 0600 파일 권한
- PostgreSQL psycopg 드라이버 로딩 및 SQL dialect 컴파일
- JavaScript syntax (`node --check`), shell syntax (`bash -n`), Python 컴파일
- 운영/테스트 Compose YAML 파싱

테스트 도구에서 Starlette의 httpx 호환 경로에 대한 deprecation warning 1개가 발생했습니다. 테스트 실패는 없습니다.

## 이 환경에서 미실행

- Docker 이미지 build와 컨테이너 시작: Docker 미설치
- 실제 PostgreSQL 17 통합 테스트: 별도 서버 실행 권한 제한
- 실제 pg_dump/pg_restore 왕복 테스트 및 Ubuntu/Debian APT/systemd 설치
- 브라우저 화면 렌더링/클릭 시각 검증: 브라우저 QA 도구 미사용
- 회사 프록시/이미지 저장소/방화벽/HTTPS 연결 및 실제 스캔 스킬 연동
- 실제 대규모 데이터 성능 측정과 MD 양식별 필드 추출

## 운영 서버의 다음 검증

1. 사내 프록시와 저장소 설정 후 `scripts/install.sh --port 9999`.
2. `scripts/manage.sh test`로 운영 DB와 분리된 PostgreSQL 17 컨테이너 통합 테스트.
3. 웹 수동 등록: MD 1개 / 정상 완료 0건 / 실패 실행을 각각 등록.
4. MD 열람, 담당자·판단·수정 진행·댓글 변경과 통계/CSV 확인.
5. 스캔 장비에서 `scripts/upload.py`로 등록 후 같은 ID 재전송 중복 방지 확인.
6. 백업 후 별도 검증 서버에서 복원하고 MD·상태·이력 확인.

실제 서버에 접근하거나 배포한 상태는 아닙니다. 프로젝트 소스와 설치/검증 명령을 제공하는 초기 구현입니다.
