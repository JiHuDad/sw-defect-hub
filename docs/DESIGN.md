# 설계 · 0.1.0

## 확정한 요구사항

1. Ubuntu/Debian 사내 서버, sudo 또는 관리자 지원 가능
2. 사내 프록시/패키지 저장소로 설치, Git에서 관리할 수 있는 프로젝트
3. 릴리스(SVR26B 등)와 브랜치(INTEG, REL COMMON 등)를 분리
4. 파트 VP/OP/FS/RS/NP/DS/Security 아래 CL 검사 결과 탐색
5. 해당 CL 변경 코드 중심 검사, Finding MD 하나가 검출 항목 하나
6. 정상 완료 Finding 0건도 실행으로 등록, 같은 CL 재실행은 이력 모두 보관
7. 자동 업로드 API와 웹 수동 업로드 모두 지원
8. 로그인 없이 팀 공동 검토: 결함 판단, 수정 진행, 담당자, 의견, 이력
9. 버전/파트별 검출 건수와 실제 결함·오탐 비율
10. 재검출 연결은 초기 범위 제외

초기 ‘폴더 감시’ 아이디어는 완료된 결과의 웹/API 업로드 방식으로 정리했습니다. 폴더 경로나 MD 양식에 의존하지 않습니다.

## 구성

브라우저와 업로드 클라이언트 → Nginx(9999 포트) → FastAPI → PostgreSQL.
브라우저는 서버가 제공하는 HTML/CSS/JavaScript를 사용합니다. 별도 프런트엔드 빌드나 CDN이 없습니다.
자동 업로드는 Bearer 토큰, 웹 변경은 같은 origin과 사용자 정의 헤더를 확인합니다. 웹 로그인은 아닙니다.
데이터베이스와 앱 포트는 호스트에 공개하지 않고 웹 포트만 공개합니다.

## 데이터 모델

| 엔티티 | 주요 항목 | 관계/제약 |
|---|---|---|
| Run | 실행 ID, 릴리스, 브랜치, 파트, CL, 상태, 등록자, 시각, 도구/모델/메모, 콘텐츠 지문 | 실행 ID 전역 유일; 동일 CL에 여러 실행 가능 |
| Finding | 파일명, 제목, 원본 MD, SHA-256, 판단, 수정 진행, 담당자, revision | Run당 파일명 유일 |
| Event | 작성자, 시각, 상태 변경 전후 값 또는 댓글 | Finding에 연결; 기존 이벤트 수정 API 없음 |

릴리스·브랜치·파트·CL·실행 ID에 인덱스를 두고 집계는 SQL에서 처리합니다.
목록은 페이지당 30 실행, Finding과 이력은 페이지당 50개, 탐색 목록은 페이지당 200개입니다.
원본 MD를 UTF-8 텍스트로 DB에 저장하고 다운로드 시 UTF-8로 재구성합니다. BOM/CRLF도 보존합니다.
등록 시 MD와 Run은 한 DB 트랜잭션으로 커밋합니다. 파일과 DB 사이의 부분 완료가 없습니다.

## 실행 ID와 재시도

- 실행 ID는 릴리스·CL과 별개로 고유해야 합니다. UUID 또는 분류를 포함한 고유 문자열 사용.
- 같은 실행 ID + 같은 메타데이터/파일명/원문: 기존 결과 반환.
- 파일 전송 순서는 중복 판정에 영향을 주지 않습니다.
- 같은 실행 ID + 다른 내용: HTTP 409. 원본과 검토 상태를 덮어쓰지 않습니다.
- 실제 재스캔: 새 실행 ID로 Run과 Findings 생성. 이전 검토 결과는 이전 실행에 남깁니다.
- 동시에 같은 ID 업로드: DB unique 제약으로 중복 방지 후 기존 결과 재확인.

## 상태

Run 상태는 completed(정상 완료), failed(실패), cancelled(중단).
파일 없는 completed는 `no_findings=true`가 필요합니다.
failed/cancelled의 파일 없음은 Finding 0건 정상 완료가 아닙니다.
실패 시 부분 MD도 보관할 수 있지만 정상 완료 Finding 통계에는 포함하지 않습니다.

Finding 판단: unreviewed, confirmed, false_positive, deferred.
Finding 처리 결과: open, in_progress, wont_fix, fixed, verified. Fixed/verified에는 수정 CL(fix_cl)이 필요합니다.
결함 판단과 처리 결과를 함께 기록합니다. false_positive는 Closed이며, 실제 결함의 wont_fix/fixed/verified도 Closed입니다. 나머지는 Open입니다. fixed/verified/wont_fix는 confirmed 판단이 필요하며, 검토 상태 변경은 revision이 일치할 때만 저장합니다.
댓글과 상태 변경 이벤트는 작성자 이름/UTC 시각을 기록합니다. 화면 시각은 브라우저 현지 시간으로 표시합니다.

## 통계 기준

| 지표 | 정의 |
|---|---|
| 실행 수 | 선택 범위의 Run 수 (실패/중단 포함) |
| 정상 완료/실패/중단 | Run 상태별 수 |
| Finding 수 | 선택 범위의 completed Run에 연결된 MD 수 |
| 실제 결함/오탐/미검토/보류 | completed Run Finding 판단별 수 |
| 오탐률 | 오탐 / (실제 결함 + 오탐) × 100 |
| 검토율 | (실제 결함 + 오탐) / Finding 수 × 100 |

분모가 0이면 0% 대신 ‘—’(정의 불가)를 표시합니다. 보류는 판정 완료가 아닙니다.
‘전체 실행’은 재검사 Findings를 각각 집계하며 고유 결함 수를 의미하지 않습니다.
‘CL별 최신’은 릴리스/브랜치/파트/CL 조합별 마지막 **등록 실행**을 사용합니다. 스캔 종료 시각이 아닙니다.
최신 실행이 실패하면 그 CL의 이전 정상 완료 Findings를 현재 통계로 대체하지 않습니다.
두 범위 모두 이전 실행과 검토 이력은 보존합니다.

## 파일 처리

MD만 허용, 실행당 100개/합계 50 MiB, 파일당 5 MiB, UTF-8 필수.
Nginx 요청 제한은 multipart 부가정보를 포함해 60 MiB입니다.
경로/제어문자/중복 파일명과 빈 파일·바이너리를 거부합니다.
HTML은 Markdown 렌더링에서 비활성화하고 결과도 허용 태그로 정리합니다.
외부 이미지 렌더링은 비활성화합니다. 코드 보고서를 열 때 외부 서버로 자동 요청하지 않습니다.
CSV 문자열은 수식으로 실행되지 않도록 시작 문자에 따라 이스케이프합니다.

## 미확정/운영 전 확인

- 실제 MD 예시: 제목 외 필드 추출은 아직 도입하지 않음
- 회사 프록시·이미지 주소·인증서, 접속 URL/방화벽: 운영 서버에서 설정 필요
- 데이터 규모: 실제 자료로 성능 측정 필요; PostgreSQL부터 사용
- 스캔 스킬 연결: 업로드 클라이언트 호출 규약은 제공, 기존 스킬 코드는 전달되지 않음
- 담당자 이름/작성자 신원: 현재 자기 기입; 권한 분리·SSO는 후속 단계

## 기술 근거

- [FastAPI multipart 파일과 폼](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/): JSON 본문과 파일을 섞는 대신 metadata 문자열 + files multipart 사용.
- [Docker Compose Linux 설치](https://docs.docker.com/compose/install/linux/): Compose plugin 필요.
- [Docker build proxy arguments](https://docs.docker.com/build/building/variables/#proxy-arguments): 프록시 빌드 인자는 Dockerfile에 다시 선언하지 않음.
- [Docker build secrets](https://docs.docker.com/build/building/secrets/): pip 저장소 설정은 이미지 ENV/ARG 대신 build secret 전달.

## 수정 CL 스키마 갱신

앱 시작 시 `app/migrations.py`가 기존 Finding 테이블에 없는 `fix_cl` 컬럼만 추가합니다. 기존 원문·판단·revision·이력을 유지하며 반복 실행해도 컬럼을 중복 추가하지 않습니다. PostgreSQL에서는 트랜잭션 advisory lock으로 앱 작업자 간 스키마 갱신을 직렬화합니다.
기존 Fixed/verified에 수정 CL이 없었다면 값을 추정하지 않습니다. Closed를 유지하되 다음 검토 저장 시 실제 수정 CL을 입력해야 합니다. 운영 업데이트 전 DB 백업은 계속 필요합니다.
