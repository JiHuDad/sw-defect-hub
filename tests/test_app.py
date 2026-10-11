import json
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

HEADERS = {'X-Requested-With': 'DefectHub', 'Origin': 'http://testserver'}


@pytest.fixture
def client(tmp_path):
    url = os.getenv('TEST_DATABASE_URL')
    admin = None
    if url:
        admin = create_engine(url)
        schema = 'test_' + uuid.uuid4().hex
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
        url = make_url(url).update_query_dict({'options': '-csearch_path=' + schema})
    else:
        url = f'sqlite:///{tmp_path}/test.db'
    try:
        app = create_app(url, upload_token='test-upload-token')
        with TestClient(app) as client:
            yield client
    finally:
        if admin:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
            admin.dispose()


def metadata(**overrides):
    return {'execution_id': 'scan-001', 'release': 'SVR26B', 'branch': 'REL COMMON',
            'part': 'NP', 'cl': '123456', 'uploader': 'tester', **overrides}


def upload(client, meta=None, files=None, manual=False):
    meta = meta or metadata()
    files = files if files is not None else [('files', ('finding.md', b'# Finding\nBody', 'text/markdown'))]
    return client.post('/api/manual/runs' if manual else '/api/runs',
                       data={'metadata': json.dumps(meta)}, files=files,
                       headers=HEADERS if manual else {'Authorization': 'Bearer test-upload-token'})


def finding_id(client, run_id):
    return client.get(f'/api/runs/{run_id}').json()['findings'][0]['id']


def test_both_upload_paths_and_zero_findings(client):
    first = upload(client, manual=True)
    assert first.status_code == 200, first.text
    second = upload(client, metadata(execution_id='empty', no_findings=True), files=[])
    assert second.status_code == 200, second.text
    assert client.get('/api/runs/'+str(second.json()['id'])).json()['finding_count'] == 0
    groups = client.get('/api/groups?level=cl&release=SVR26B&branch=REL%20COMMON&part=NP').json()
    assert groups == [{'name': '123456', 'runs': 2, 'findings': 1}]
    assert client.get('/api/groups?page=2').json() == []
    assert client.get('/api/groups?page=0').status_code == 422


def test_idempotent_retries_and_new_execution_history(client):
    first = upload(client).json()
    repeated = upload(client).json()
    assert repeated['duplicate'] and first['id'] == repeated['id']
    conflict = upload(client, files=[('files', ('finding.md', b'# Different', 'text/markdown'))])
    assert conflict.status_code == 409
    second = upload(client, metadata(execution_id='scan-002')).json()
    assert second['id'] != first['id']
    assert client.get('/api/runs').json()['total'] == 2


def test_manifest_order_does_not_break_retry(client):
    files = [('files', ('b.md', b'# B', 'text/markdown')), ('files', ('a.md', b'# A', 'text/markdown'))]
    assert upload(client, files=files).status_code == 200
    assert upload(client, files=list(reversed(files))).json()['duplicate'] is True


@pytest.mark.parametrize('meta,files', [
    (metadata(no_findings=False), []),
    (metadata(no_findings=True), None),
    (metadata(status='failed', no_findings=True), []),
    (metadata(part='UNKNOWN'), None),
    (metadata(cl='0'), None),
    (metadata(started_at='2026-10-11T11:00:00'), None),
    (metadata(started_at='2026-10-11T11:00:00+09:00', finished_at='2026-10-10T11:00:00+09:00'), None),
    (metadata(uploader='   '), None),
])
def test_invalid_metadata_is_atomic(client, meta, files):
    assert upload(client, meta, files).status_code == 422
    assert client.get('/api/runs').json()['total'] == 0


@pytest.mark.parametrize('filename,content', [('bad.txt', b'hi'), ('../x.md', b'hi'), ('x.md', b'\xff'),
    ('x.md', b''), ('x.md', b'\x00hi'), ('a\\b.md', b'hi')])
def test_invalid_files_are_rejected(client, filename, content):
    assert upload(client, files=[('files', (filename, content))]).status_code == 422
    assert client.get('/api/runs').json()['total'] == 0


def test_file_limit_and_duplicate_names(client):
    assert upload(client, files=[('files', ('x.md', b'x'*(5*1024*1024+1)))]).status_code == 413
    assert upload(client, files=[('files', ('x.md', b'one')), ('files', ('x.md', b'two'))]).status_code == 422


def test_token_and_browser_origin(client):
    assert client.post('/api/runs', data={'metadata': json.dumps(metadata())}).status_code == 401
    assert client.post('/api/manual/runs', data={'metadata': json.dumps(metadata())}).status_code == 403
    assert client.post('/api/manual/runs', data={'metadata': json.dumps(metadata())},
                       headers={'X-Requested-With': 'DefectHub', 'Origin': 'https://evil.test'}).status_code == 403


def test_safe_markdown_and_exact_original_download(client):
    content = '\ufeff# 한글 제목\r\n<script>alert(1)</script>\r\n[x](javascript:alert(1))\n![img](https://external.test/a.png)\n'.encode()
    run = upload(client, files=[('files', ('한글.md', content))]).json()
    id = finding_id(client, run['id'])
    item = client.get(f'/api/findings/{id}').json()
    assert '<script>' not in item['html'] and 'href="javascript:' not in item['html'] and '<img' not in item['html']
    assert item['title'] == '한글 제목'
    raw = client.get(f'/api/findings/{id}/raw')
    assert raw.content == content and "filename*=UTF-8''" in raw.headers['content-disposition']


def test_optimistic_review_and_comments_history(client):
    id = finding_id(client, upload(client).json()['id'])
    body = {'revision': 1, 'actor': 'Alice', 'judgment': 'confirmed', 'progress': 'in_progress', 'assignee': 'Bob'}
    saved = client.patch(f'/api/findings/{id}', json=body, headers=HEADERS)
    assert saved.status_code == 200 and saved.json()['revision'] == 2
    assert client.patch(f'/api/findings/{id}', json=body, headers=HEADERS).status_code == 409
    assert client.post(f'/api/findings/{id}/comments', json={'actor': 'Bob', 'text': '확인합니다.'}, headers=HEADERS).status_code == 200
    events = client.get(f'/api/findings/{id}/events').json()['items']
    assert len(events) == 2 and events[0]['kind'] == 'comment' and events[1]['actor'] == 'Alice'
    assert events[1]['detail']['judgment'] == {'before': 'unreviewed', 'after': 'confirmed'}
    assert client.get(f'/api/findings/{id}').json()['assignee'] == 'Bob'


def test_stats_denominators_latest_and_failures(client):
    for i, judgment in enumerate(['confirmed', 'false_positive', 'unreviewed', 'deferred']):
        id = finding_id(client, upload(client, metadata(execution_id=f'scan-{i}', cl=str(100+i))).json()['id'])
        assert client.patch(f'/api/findings/{id}', json={'revision':1, 'actor':'A', 'judgment':judgment,
                            'progress':'open','assignee':''}, headers=HEADERS).status_code == 200
    upload(client, metadata(execution_id='zero', cl='200', no_findings=True), [])
    upload(client, metadata(execution_id='failed', cl='201', status='failed'), [])
    # Failed partial reports are visible but excluded from completed-findings metrics.
    upload(client, metadata(execution_id='failed-partial', cl='202', status='failed'))
    row = client.get('/api/stats').json()['items'][0]
    assert row['runs'] == 7 and row['completed'] == 5 and row['failed'] == 2
    assert row['findings'] == 4 and row['false_positive_rate'] == 50 and row['review_rate'] == 50
    upload(client, metadata(execution_id='new-run', cl='100', no_findings=True), [])
    latest = client.get('/api/stats?mode=latest').json()['items'][0]
    assert latest['runs'] == 7 and latest['findings'] == 3 and latest['confirmed'] == 0
    assert latest['false_positive_rate'] == 100
    assert client.get('/api/stats?release=OTHER').json()['items'] == []


def test_pagination_search_and_csv_escape(client):
    for i in range(31):
        assert upload(client, metadata(execution_id=f'run-{i}', release='=HYPERLINK(1)', cl=str(i+1), no_findings=True), []).status_code == 200
    first = client.get('/api/runs').json();second = client.get('/api/runs?page=2').json()
    assert first['total'] == 31 and len(first['items']) == 30 and len(second['items']) == 1
    assert client.get('/api/runs?q=run-30').json()['total'] == 1
    assert client.get('/api/runs?q=%25').json()['total'] == 0
    csv = client.get('/api/stats.csv')
    assert csv.content.startswith(b'\xef\xbb\xbf') and "'=HYPERLINK(1)" in csv.text


def test_missing_resources_and_static_security(client):
    for url in ['/api/runs/999', '/api/findings/999', '/api/findings/999/raw', '/api/findings/999/events']:
        assert client.get(url).status_code == 404
    response = client.get('/')
    assert response.status_code == 200 and 'SW Defect Hub' in response.text
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert client.get('/healthz').json()['status'] == 'ok'


def test_part_groups_include_empty_parts_and_keep_scoped_counts(client):
    parts = ['VP', 'OP', 'FS', 'RS', 'NP', 'DS', 'Security']
    empty = client.get('/api/groups?level=part&release=SVR26B&branch=INTEG').json()
    assert empty == [{'name': name, 'runs': 0, 'findings': 0} for name in parts]
    assert upload(client, metadata(branch='INTEG', part='VP')).status_code == 200
    assert upload(client, metadata(execution_id='zero-op', branch='INTEG', part='OP', no_findings=True), []).status_code == 200
    assert upload(client, metadata(execution_id='other-release', release='SVR27A', branch='INTEG', part='VP')).status_code == 200
    rows = client.get('/api/groups?level=part&release=SVR26B&branch=INTEG').json()
    assert [row['name'] for row in rows] == parts
    assert rows[0] == {'name': 'VP', 'runs': 1, 'findings': 1}
    assert rows[1] == {'name': 'OP', 'runs': 1, 'findings': 0}
    assert all(row['runs'] == row['findings'] == 0 for row in rows[2:])
    assert client.get('/api/groups?level=part&release=SVR26B&branch=INTEG&page=2').json() == []
    assert client.get('/api/groups?level=cl&release=SVR26B&branch=INTEG&part=FS').json() == []


def test_resolution_closure_fix_cl_reopen_history_and_stats(client):
    id = finding_id(client, upload(client).json()['id'])
    endpoint = f'/api/findings/{id}'
    base = {'actor': 'Reviewer', 'assignee': 'Owner', 'judgment': 'confirmed'}
    assert client.get(endpoint).json()['status'] == 'open'
    transitions = [
        {'judgment': 'false_positive', 'progress': 'open', 'fix_cl': '', 'status': 'closed'},
        {'judgment': 'confirmed', 'progress': 'wont_fix', 'fix_cl': '', 'status': 'closed'},
        {'judgment': 'confirmed', 'progress': 'fixed', 'fix_cl': '98765', 'status': 'closed'},
        {'judgment': 'confirmed', 'progress': 'verified', 'fix_cl': '98765', 'status': 'closed'},
        {'judgment': 'confirmed', 'progress': 'open', 'fix_cl': '', 'status': 'open'},
    ]
    for revision, state in enumerate(transitions, 1):
        expected_status = state['status']
        body = base | {k: v for k, v in state.items() if k != 'status'} | {'revision': revision}
        saved = client.patch(endpoint, json=body, headers=HEADERS)
        assert saved.status_code == 200, saved.text
        result = saved.json()
        assert result['status'] == expected_status and result['fix_cl'] == state['fix_cl']
        assert result['resolution'] == ('false_positive' if state['judgment'] == 'false_positive' else state['progress'] if expected_status == 'closed' else None)
        listed = client.get(f'/api/runs/{result["run_id"]}').json()['findings'][0]
        assert listed['status'] == expected_status and listed['fix_cl'] == state['fix_cl']
        stats = client.get('/api/stats').json()['items'][0]
        assert stats['closed'] == int(expected_status == 'closed')
        assert stats['open'] + stats['closed'] == stats['findings'] == 1
    events = client.get(endpoint+'/events').json()['items']
    assert events[0]['detail']['status'] == {'before': 'closed', 'after': 'open'}
    assert events[-1]['detail']['status'] == {'before': 'open', 'after': 'closed'}
    assert events[0]['detail']['fix_cl'] == {'before': '98765', 'after': ''}
    assert events[2]['detail']['fix_cl'] == {'before': '', 'after': '98765'}
    stale = client.patch(endpoint, json=base | {'revision': 1, 'progress': 'fixed', 'fix_cl': '123'}, headers=HEADERS)
    assert stale.status_code == 409 and client.get(endpoint).json()['status'] == 'open'
    assert len(client.get(endpoint+'/events').json()['items']) == 5
    assert 'open,closed' in client.get('/api/stats.csv').text


@pytest.mark.parametrize('judgment,progress,fix_cl', [
    ('confirmed', 'fixed', ''), ('confirmed', 'verified', ''),
    ('confirmed', 'fixed', '0'), ('confirmed', 'fixed', 'abc'),
    ('confirmed', 'fixed', '1; DROP TABLE findings'),
    ('confirmed', 'wont_fix', '123'), ('confirmed', 'open', '123'),
    ('false_positive', 'fixed', '123'), ('unreviewed', 'wont_fix', ''),
])
def test_invalid_resolution_is_atomic(client, judgment, progress, fix_cl):
    id = finding_id(client, upload(client).json()['id'])
    body = {'revision': 1, 'actor': 'Reviewer', 'judgment': judgment, 'progress': progress, 'fix_cl': fix_cl}
    assert client.patch(f'/api/findings/{id}', json=body, headers=HEADERS).status_code == 422
    item = client.get(f'/api/findings/{id}').json()
    assert item['revision'] == 1 and item['status'] == 'open' and item['fix_cl'] == ''
    assert client.get(f'/api/findings/{id}/events').json()['total'] == 0
