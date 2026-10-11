import csv
import hashlib
import hmac
import io
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import bleach
from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select, func, update, exists
from sqlalchemy.exc import IntegrityError

from .models import Base, Run, Finding, Event, database

PARTS = ['VP', 'OP', 'FS', 'RS', 'NP', 'DS', 'Security']
JUDGMENTS = ['unreviewed', 'confirmed', 'false_positive', 'deferred']
PROGRESS = ['open', 'in_progress', 'fixed', 'verified']
STATIC = Path(__file__).parent / 'static'


class Metadata(BaseModel):
    model_config = {'extra': 'forbid'}
    execution_id: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.:-]+$')
    release: str = Field(min_length=1, max_length=80)
    branch: str = Field(min_length=1, max_length=80)
    part: Literal['VP', 'OP', 'FS', 'RS', 'NP', 'DS', 'Security']
    cl: str = Field(pattern=r'^[1-9][0-9]{0,19}$')
    status: Literal['completed', 'failed', 'cancelled'] = 'completed'
    uploader: str = Field(min_length=1, max_length=80)
    no_findings: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    tool: str = Field(default='', max_length=200)
    model: str = Field(default='', max_length=200)
    notes: str = Field(default='', max_length=10000)
    error: str = Field(default='', max_length=10000)

    @field_validator('release', 'branch', 'uploader')
    @classmethod
    def clean(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('공백 또는 제어문자는 사용할 수 없습니다.')
        return value.strip()

    @model_validator(mode='after')
    def times(self):
        for value in (self.started_at, self.finished_at):
            if value and value.utcoffset() is None:
                raise ValueError('시각에는 시간대가 필요합니다. 예: +09:00')
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError('종료 시각은 시작 시각 이후여야 합니다.')
        if self.status != 'completed' and self.no_findings:
            raise ValueError('실패·중단은 Finding 0개 정상 완료가 아닙니다.')
        return self


class Review(BaseModel):
    model_config = {'extra': 'forbid'}
    revision: int = Field(ge=1)
    actor: str = Field(min_length=1, max_length=80)
    judgment: Literal['unreviewed', 'confirmed', 'false_positive', 'deferred']
    progress: Literal['open', 'in_progress', 'fixed', 'verified']
    assignee: str = Field(default='', max_length=80)

    @field_validator('actor')
    @classmethod
    def actor_required(cls, value):
        if not value.strip():
            raise ValueError('작성자 이름이 필요합니다.')
        return value.strip()


class Comment(BaseModel):
    model_config = {'extra': 'forbid'}
    actor: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=10000)

    @field_validator('actor', 'text')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('내용을 입력하세요.')
        return value.strip()


def safe_markdown(text):
    html = MarkdownIt('commonmark', {'html': False, 'linkify': False}).enable('table').render(text)
    return bleach.clean(html, tags=['p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol',
        'li', 'blockquote', 'pre', 'code', 'em', 'strong', 'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 's'],
        attributes={'a': ['href', 'title'], 'code': ['class']}, protocols=['http', 'https', 'mailto'], strip=True)


def create_app(database_url=None, upload_token=None):
    engine, Sessions = database(database_url)
    token = upload_token if upload_token is not None else os.getenv('UPLOAD_TOKEN', '')

    @asynccontextmanager
    async def lifespan(app):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title='SW Defect Hub', version='0.1.0', lifespan=lifespan)
    app.state.engine = engine
    app.state.sessions = Sessions
    app.mount('/static', StaticFiles(directory=STATIC), name='static')

    @app.middleware('http')
    async def security(request, call_next):
        # Browser mutations require a custom header and same-origin when Origin is present.
        if request.method in {'POST', 'PATCH', 'DELETE', 'PUT'} and request.url.path != '/api/runs':
            origin = request.headers.get('origin')
            allowed = {str(request.base_url).rstrip('/'), os.getenv('PUBLIC_URL', '').rstrip('/')}
            if request.headers.get('x-requested-with') != 'DefectHub' or (origin and origin not in allowed):
                return Response('동일한 웹 화면에서 요청하세요.', status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api') else 'no-cache'
        return response

    def db():
        with Sessions() as session:
            yield session

    def automation(request: Request):
        if not token:
            raise HTTPException(503, '자동 업로드 토큰이 설정되지 않았습니다.')
        provided = request.headers.get('authorization', '')
        if not hmac.compare_digest(provided, 'Bearer ' + token):
            raise HTTPException(401, '업로드 토큰이 올바르지 않습니다.')

    @app.get('/')
    def index():
        return FileResponse(STATIC / 'index.html')

    @app.get('/healthz')
    def health(session=Depends(db)):
        session.execute(select(1))
        return {'status': 'ok', 'version': '0.1.0'}

    @app.get('/api/config')
    def config():
        return {'parts': PARTS, 'judgments': JUDGMENTS, 'progress': PROGRESS,
                'max_file_bytes': 5 * 1024 * 1024, 'max_files': 100}

    def filters(release='', branch='', part='', cl=''):
        return [getattr(Run, key) == value for key, value in
                [('release', release), ('branch', branch), ('part', part), ('cl', cl)] if value]

    def run_data(run, count=0):
        return {key: getattr(run, key) for key in ('id', 'execution_id', 'release', 'branch', 'part',
                'cl', 'status', 'uploader', 'started_at', 'finished_at', 'created_at')} | {'finding_count': count}

    def finding_data(item):
        return {key: getattr(item, key) for key in ('id', 'run_id', 'filename', 'title', 'judgment',
                                                   'progress', 'assignee', 'revision', 'sha256')}

    def scoped_ids(release='', branch='', part='', cl='', mode='all'):
        scope = filters(release, branch, part, cl)
        if mode == 'latest':
            return select(func.max(Run.id)).where(*scope).group_by(Run.release, Run.branch, Run.part, Run.cl)
        return select(Run.id).where(*scope)

    @app.get('/api/groups')
    def groups(level: Literal['release', 'branch', 'part', 'cl'] = 'release', release: str = '',
               branch: str = '', part: str = '', page: int = 1, session=Depends(db)):
        if page < 1:
            raise HTTPException(422, '페이지 번호를 확인하세요.')
        column = getattr(Run, level)
        # Count findings per run before grouping; zero-finding runs must remain visible.
        counts = select(Finding.run_id, func.count().label('n')).group_by(Finding.run_id).subquery()
        query = select(column, func.count(Run.id), func.coalesce(func.sum(counts.c.n), 0)).outerjoin(
            counts, counts.c.run_id == Run.id).where(*filters(release, branch, part)).group_by(column).order_by(column).offset((page - 1) * 200).limit(200)
        items = [{'name': name, 'runs': int(runs), 'findings': int(n)} for name, runs, n in session.execute(query)]
        if level == 'part' and page == 1:
            by_name = {item['name']: item for item in items}
            return [by_name.get(name, {'name': name, 'runs': 0, 'findings': 0}) for name in PARTS]
        return items

    @app.get('/api/runs')
    def runs(release: str = '', branch: str = '', part: str = '', cl: str = '', q: str = '',
             page: int = 1, session=Depends(db)):
        if page < 1 or len(q) > 200:
            raise HTTPException(422, '검색 조건을 확인하세요.')
        conditions = filters(release, branch, part, cl)
        if q:
            pattern = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            conditions.append(Run.cl.ilike(pattern, escape='\\') | Run.execution_id.ilike(pattern, escape='\\') |
                exists(select(Finding.id).where(Finding.run_id == Run.id,
                    Finding.markdown.ilike(pattern, escape='\\'))))
        total = session.scalar(select(func.count()).select_from(Run).where(*conditions))
        counts = select(Finding.run_id, func.count().label('n')).group_by(Finding.run_id).subquery()
        rows = session.execute(select(Run, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.run_id == Run.id)
            .where(*conditions).order_by(Run.id.desc()).offset((page - 1) * 30).limit(30))
        return {'items': [run_data(r, n) for r, n in rows], 'total': total, 'page': page, 'page_size': 30}

    @app.get('/api/runs/{run_id}')
    def run_detail(run_id: int, page: int = 1, session=Depends(db)):
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(404, '실행 결과가 없습니다.')
        if page < 1:
            raise HTTPException(422, '페이지 번호를 확인하세요.')
        count = session.scalar(select(func.count()).select_from(Finding).where(Finding.run_id == run_id))
        items = session.scalars(select(Finding).where(Finding.run_id == run_id).order_by(Finding.id)
                                .offset((page - 1) * 50).limit(50))
        return run_data(run, count) | {'metadata': json.loads(run.metadata_json),
               'findings': [finding_data(f) for f in items], 'page': page, 'page_size': 50}

    async def ingest(metadata, files, session):
        try:
            meta = Metadata.model_validate_json(metadata)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if len(files) > 100:
            raise HTTPException(413, '한 실행당 최대 100개 MD를 등록할 수 있습니다.')
        if meta.status == 'completed' and not files and not meta.no_findings:
            raise HTTPException(422, '정상 완료에 파일이 없다면 Finding 없음으로 명시하세요.')
        if meta.no_findings and files:
            raise HTTPException(422, 'Finding 없음과 MD 파일을 함께 등록할 수 없습니다.')
        payloads = []
        names = set()
        total = 0
        for file in files:
            name = file.filename or ''
            if not name.lower().endswith('.md') or len(name) > 240 or '/' in name or '\\' in name or any(ord(c) < 32 for c in name):
                raise HTTPException(422, '경로 없는 .md 파일명만 허용합니다.')
            if name in names:
                raise HTTPException(422, '같은 파일명을 두 번 등록할 수 없습니다.')
            names.add(name)
            raw = await file.read(5 * 1024 * 1024 + 1)
            total += len(raw)
            if len(raw) > 5 * 1024 * 1024 or total > 50 * 1024 * 1024:
                raise HTTPException(413, 'MD당 5 MiB, 실행당 50 MiB 이하로 등록하세요.')
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError as exc:
                raise HTTPException(422, 'MD는 UTF-8 인코딩이어야 합니다.') from exc
            if not text.strip() or '\x00' in text:
                raise HTTPException(422, '빈 파일 또는 바이너리 파일은 등록할 수 없습니다.')
            digest = hashlib.sha256(raw).hexdigest()
            heading = re.search(r'^#{1,6}\s+(.+)', text.lstrip('\ufeff'), re.M)
            title = (heading.group(1).strip() if heading else name)[:300]
            payloads.append((name, text, digest, title))
        canonical = meta.model_dump(mode='json')
        manifest = sorted([(n, h) for n, _, h, _ in payloads])
        fingerprint = hashlib.sha256(json.dumps([canonical, manifest], sort_keys=True,
                                                ensure_ascii=False).encode()).hexdigest()
        def existing_result(existing):
            if existing.fingerprint != fingerprint:
                raise HTTPException(409, '같은 실행 ID에 다른 내용이 있습니다. 재스캔에는 새 실행 ID를 사용하세요.')
            return {'id': existing.id, 'execution_id': existing.execution_id, 'duplicate': True,
                    'url': f'/#run={existing.id}'}
        existing = session.scalar(select(Run).where(Run.execution_id == meta.execution_id))
        if existing:
            return existing_result(existing)
        run = Run(execution_id=meta.execution_id, release=meta.release, branch=meta.branch, part=meta.part,
                  cl=meta.cl, status=meta.status, uploader=meta.uploader,
                  started_at=meta.started_at.isoformat() if meta.started_at else None,
                  finished_at=meta.finished_at.isoformat() if meta.finished_at else None,
                  metadata_json=json.dumps(canonical, ensure_ascii=False), fingerprint=fingerprint)
        try:
            session.add(run)
            session.flush()
            session.add_all([Finding(run_id=run.id, filename=n, markdown=t, sha256=h, title=title)
                             for n, t, h, title in payloads])
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(select(Run).where(Run.execution_id == meta.execution_id))
            if existing:
                return existing_result(existing)
            raise
        return {'id': run.id, 'execution_id': run.execution_id, 'duplicate': False, 'url': f'/#run={run.id}'}

    @app.post('/api/runs', dependencies=[Depends(automation)])
    async def auto_upload(metadata: str = Form(...), files: list[UploadFile] = File(default=[]), session=Depends(db)):
        return await ingest(metadata, files, session)

    @app.post('/api/manual/runs')
    async def manual_upload(metadata: str = Form(...), files: list[UploadFile] = File(default=[]), session=Depends(db)):
        return await ingest(metadata, files, session)

    @app.get('/api/findings/{finding_id}')
    def detail(finding_id: int, session=Depends(db)):
        item = session.get(Finding, finding_id)
        if not item:
            raise HTTPException(404, 'Finding이 없습니다.')
        run = session.get(Run, item.run_id)
        return finding_data(item) | {'html': safe_markdown(item.markdown), 'run': run_data(run)}

    @app.get('/api/findings/{finding_id}/raw')
    def raw(finding_id: int, session=Depends(db)):
        item = session.get(Finding, finding_id)
        if not item:
            raise HTTPException(404, 'Finding이 없습니다.')
        return Response(item.markdown.encode('utf-8'), media_type='text/markdown', headers={
            'Content-Disposition': "attachment; filename*=UTF-8''" + quote(item.filename)})

    @app.patch('/api/findings/{finding_id}')
    def review(finding_id: int, body: Review, session=Depends(db)):
        item = session.get(Finding, finding_id)
        if not item:
            raise HTTPException(404, 'Finding이 없습니다.')
        before = finding_data(item)
        after = {k: getattr(body, k) for k in ('judgment', 'progress', 'assignee')}
        result = session.execute(update(Finding).where(Finding.id == finding_id, Finding.revision == body.revision)
                                 .values(**after, revision=Finding.revision + 1))
        if result.rowcount != 1:
            session.rollback()
            raise HTTPException(409, '다른 팀원이 먼저 변경했습니다. 새로고침 후 다시 저장하세요.')
        changes = {k: {'before': before[k], 'after': v} for k, v in after.items() if before[k] != v}
        session.add(Event(finding_id=finding_id, actor=body.actor, kind='review', detail=json.dumps(changes, ensure_ascii=False)))
        session.commit()
        session.expire_all()
        return finding_data(session.get(Finding, finding_id))

    @app.get('/api/findings/{finding_id}/events')
    def events(finding_id: int, page: int = 1, session=Depends(db)):
        if not session.get(Finding, finding_id):
            raise HTTPException(404, 'Finding이 없습니다.')
        if page < 1:
            raise HTTPException(422, '페이지 번호를 확인하세요.')
        total = session.scalar(select(func.count()).select_from(Event).where(Event.finding_id == finding_id))
        rows = session.scalars(select(Event).where(Event.finding_id == finding_id).order_by(Event.id.desc())
                               .offset((page - 1) * 50).limit(50))
        return {'items': [{'id': e.id, 'actor': e.actor, 'kind': e.kind,
                          'detail': json.loads(e.detail), 'created_at': e.created_at} for e in rows], 'total': total}

    @app.post('/api/findings/{finding_id}/comments')
    def comment(finding_id: int, body: Comment, session=Depends(db)):
        if not session.get(Finding, finding_id):
            raise HTTPException(404, 'Finding이 없습니다.')
        session.add(Event(finding_id=finding_id, actor=body.actor, kind='comment',
                          detail=json.dumps({'text': body.text}, ensure_ascii=False)))
        session.commit()
        return {'ok': True}

    def stats_data(session, release='', branch='', part='', cl='', mode='all'):
        ids = scoped_ids(release, branch, part, cl, mode)
        run_rows = session.execute(select(Run.release, Run.branch, Run.part, Run.status, func.count())
                                  .where(Run.id.in_(ids)).group_by(Run.release, Run.branch, Run.part, Run.status))
        data = {}
        def row(key):
            return data.setdefault(key, {'release': key[0], 'branch': key[1], 'part': key[2], 'runs': 0,
                'completed': 0, 'failed': 0, 'cancelled': 0, 'findings': 0, **{j: 0 for j in JUDGMENTS}})
        for r, b, p, status, n in run_rows:
            item = row((r, b, p)); item['runs'] += n; item[status] += n
        finding_rows = session.execute(select(Run.release, Run.branch, Run.part, Finding.judgment, func.count())
            .join(Finding, Run.id == Finding.run_id).where(Run.id.in_(ids), Run.status == 'completed')
            .group_by(Run.release, Run.branch, Run.part, Finding.judgment))
        for r, b, p, judgment, n in finding_rows:
            item = row((r, b, p)); item['findings'] += n; item[judgment] += n
        result = []
        for key in sorted(data):
            item = data[key]
            adjudicated = item['confirmed'] + item['false_positive']
            item['false_positive_rate'] = round(100 * item['false_positive'] / adjudicated, 1) if adjudicated else None
            item['review_rate'] = round(100 * adjudicated / item['findings'], 1) if item['findings'] else None
            result.append(item)
        return result

    @app.get('/api/stats')
    def stats(release: str = '', branch: str = '', part: str = '', cl: str = '',
              mode: Literal['all', 'latest'] = 'all', session=Depends(db)):
        return {'items': stats_data(session, release, branch, part, cl, mode), 'mode': mode,
                'basis': '정상 완료 실행의 Finding만 집계. 오탐률=오탐/(실제 결함+오탐). 보류·미검토 제외. latest는 CL별 마지막 등록 실행.'}

    @app.get('/api/stats.csv')
    def stats_csv(release: str = '', branch: str = '', part: str = '', cl: str = '',
                  mode: Literal['all', 'latest'] = 'all', session=Depends(db)):
        rows = stats_data(session, release, branch, part, cl, mode)
        columns = ['release', 'branch', 'part', 'runs', 'completed', 'failed', 'cancelled', 'findings',
                   *JUDGMENTS, 'false_positive_rate', 'review_rate']
        output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=columns); writer.writeheader()
        # Protect spreadsheet users from CSV formula injection in free-form labels.
        for item in rows:
            writer.writerow({k: ("'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v)
                             for k, v in item.items()})
        return Response(('\ufeff' + output.getvalue()).encode('utf-8'), media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="defect-statistics.csv"'})

    return app


app = create_app()
