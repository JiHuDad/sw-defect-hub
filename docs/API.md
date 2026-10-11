# API · 스캔 스킬 연결

API 탐색: 운영 서버의 `/docs` (FastAPI OpenAPI). 사내망에서 사용합니다.

## 자동 업로드

`POST /api/runs`

헤더: `Authorization: Bearer <UPLOAD_TOKEN>`.
본문: `multipart/form-data`, `metadata` 필드에 JSON 문자열, `files`에 MD 파일 0~100개.
웹 수동 업로드는 `/api/manual/runs`를 사용하고 같은 등록 검증/트랜잭션을 거칩니다.

```json
{
  "execution_id": "svr26b-rel-common-np-cl123456-run001",
  "release": "SVR26B",
  "branch": "REL COMMON",
  "part": "NP",
  "cl": "123456",
  "status": "completed",
  "uploader": "scan-skill",
  "no_findings": false,
  "started_at": "2026-10-11T10:00:00+09:00",
  "finished_at": "2026-10-11T10:20:00+09:00",
  "tool": "defect-finding",
  "model": "",
  "notes": "changed-code scan",
  "error": ""
}
```

필수: execution_id, release, branch, part, cl, uploader.
시각은 선택이며 입력한다면 시간대를 포함해야 합니다. status 기본값은 completed.
MD 없는 completed에는 no_findings=true가 필수. 실패/중단에는 true를 사용하지 않습니다.
CL은 양의 정수를 문자열로 전송합니다. Branch의 공백도 지원합니다.

성공 응답:

```json
{"id": 1, "execution_id": "...", "duplicate": false, "url": "/#run=1"}
```

동일 내용 재전송은 duplicate=true. 클라이언트는 원래 metadata 값과 파일을 유지해야 합니다.
재시도마다 현재 시각이나 uploader를 변경하면 다른 내용으로 취급합니다.

| HTTP | 의미 |
|---|---|
| 200 | 등록 성공 또는 동일 결과 재전송 |
| 401 | 자동 업로드 토큰 누락/불일치 |
| 409 | 같은 실행 ID에 다른 내용, 또는 상태 변경 충돌 |
| 413 | 업로드 크기/파일 수 초과 |
| 422 | 분류·메타데이터·파일 검증 실패 |
| 503 | 서버에 자동 업로드 토큰 미설정 |

## 기존 스캔 스킬에 연결하기

1. 검사 시작 시 실행 ID 생성 (`uuid.uuid4()` 등), 결과 폴더에 보관.
2. 릴리스·브랜치·파트·CL을 검사 입력에서 확보.
3. 스캔 종료 후 생성된 Finding MD만 수집. 실행 로그/요약 MD를 Finding으로 전송하지 않음.
4. Finding이 없으면 --no-findings, 스캔 실패면 --status failed와 --error 지정.
5. `scripts/upload.py`를 인자 배열로 호출. shell 문자열 연결로 실행하지 않음.
6. 업로드 실패 시 결과와 ID를 유지. 검사 자체를 다시 수행하지 말고 업로드만 재시도.
7. 성공 응답 URL을 스킬 결과에 표시.

예시 (스킬의 Python 단계):

```python
import subprocess

command = [
    "python3", "/path/to/sw-defect-hub/scripts/upload.py",
    "--run-id", execution_id,
    "--release", release, "--branch", branch, "--part", part,
    "--cl", str(cl), "--uploader", "scan-skill",
]
if scan_failed:
    command += ["--status", "failed", "--error", error_text]
elif not finding_paths:
    command += ["--no-findings"]
command += [str(p) for p in finding_paths]
subprocess.run(command, check=True)  # 환경에서 URL과 토큰 주입
```

이 프로젝트는 스캔 스킬의 연결 코드와 호출 규약을 제공합니다. 실제 기존 스킬 수정은 그 소스가 있어야 수행할 수 있습니다.

## 조회/검토

| API | 용도 |
|---|---|
| GET /api/groups?level=release\|branch\|part\|cl | 단계별 탐색 (page, 페이지당 200개) |
| GET /api/runs | release/branch/part/cl/q 필터, page 페이지 |
| GET /api/runs/{id} | 실행 메타데이터와 Findings (page) |
| GET /api/findings/{id} | 렌더링 HTML 및 검토 상태 |
| GET /api/findings/{id}/raw | 원본 MD 다운로드 |
| PATCH /api/findings/{id} | revision, actor, judgment, progress, assignee, fix_cl |
| POST /api/findings/{id}/comments | actor, text |
| GET /api/findings/{id}/events | 의견·변경 이력 (page) |
| GET /api/stats | 분류 필터 및 mode=all\|latest |
| GET /api/stats.csv | 같은 기준 CSV |
| GET /healthz | DB 연결 포함 상태 확인 |

웹 변경 API에는 `X-Requested-With: DefectHub`가 필요하며 Origin이 있으면 같은 origin이어야 합니다.
상태 변경 요청은 마지막 조회의 revision을 전달해야 합니다. 409이면 새 상태를 읽고 사용자가 다시 판단합니다.
자동 업로드 토큰은 사용자 계정 인증 수단이 아닙니다.

## Finding 종료와 수정 CL

조회 응답에 `status`(open/closed), `resolution`(false_positive/wont_fix/fixed/verified 또는 null), `fix_cl`을 제공합니다. 상태는 판단·처리 결과에서 계산하므로 서로 다른 Open/Closed 값을 별도로 저장하지 않습니다.

```json
{"revision": 2, "actor": "검토자", "judgment": "confirmed", "progress": "fixed", "fix_cl": "123789", "assignee": "담당자"}
```

- `judgment=false_positive`, `progress=open`, `fix_cl=""`: 오탐으로 Closed. progress=open은 내부 수정 진행 값이며 종료 상태는 status=closed입니다.
- `judgment=confirmed`, `progress=wont_fix`, `fix_cl=""`: 수정하지 않기로 결정, Closed.
- `judgment=confirmed`, `progress=fixed|verified`: 양의 정수 문자열 수정 CL 필수, Closed.
- 그 외 `progress=open|in_progress`: Open. 보류·미검토는 종료가 아닙니다.
- 재오픈 시 판단을 false_positive 이외로 바꾸고 progress=open|in_progress, fix_cl=""를 전송합니다. 이전 수정 CL과 종료 상태는 변경 이력에 남습니다.
- 수정/검증 완료·Won’t fix는 실제 결함 판단이 필요합니다. 모순된 상태나 잘못된 수정 CL은 422로 거부하며 revision/이력을 변경하지 않습니다.
- 통계와 CSV에 `open`, `closed` 건수를 추가했습니다. 기존과 같이 정상 완료 실행의 Findings만 집계합니다. Won’t fix/Fixed는 실제 결함 통계에 남고 오탐은 오탐 통계에 남습니다.
