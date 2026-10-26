import json
import subprocess
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from io import BytesIO
from unittest.mock import Mock

import pytest
import requests
from app import create_app
from news import ResearchError, collect, parse_feed, summarize
from reports import build_pdf
from store import Store
from worker import Worker, scheduled_day

NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)


def feed(title='Boryszew inwestuje', url='https://example.com/news', date=NOW):
    return f'''<rss version="2.0"><channel><item><title>{title}</title><link>{url}</link>
    <pubDate>{format_datetime(date)}</pubDate><source>Prensa</source>
    <description>Nuevo proyecto industrial.</description></item></channel></rss>'''.encode()


def article():
    return parse_feed(feed(), 'Prensa', NOW-timedelta(days=1), NOW)[0]


def report():
    a = {**article(), 'title_es': 'Boryszew anuncia una inversión', 'summary_es': 'Resumen en español: inversión industrial.'}
    return dict(overview='Resumen del día: actualización del grupo.', articles=[a], coverage=[dict(name='Prensa',ok=True,count=1,message='Consulta completada')], omitted=0, since=(NOW-timedelta(days=1)).isoformat(),until=NOW.isoformat())


def test_dates_exclude_old_future_and_undated():
    assert len(parse_feed(feed(), 'test', NOW-timedelta(days=1), NOW)) == 1
    for date in (NOW-timedelta(days=2), NOW+timedelta(minutes=1)):
        assert not parse_feed(feed(date=date), 'test', NOW-timedelta(days=1), NOW)
    assert not parse_feed(b'<rss><channel><item><title>A</title><link>https://example.com</link></item></channel></rss>', 'test', NOW-timedelta(days=1), NOW)


def test_unsafe_links_excluded():
    assert not parse_feed(feed(url='javascript:alert(1)'), 'test', NOW-timedelta(days=1), NOW)


def test_dedup_and_partial_coverage(monkeypatch):
    response = Mock(content=feed())
    response.raise_for_status.return_value = None
    monkeypatch.setattr('news.requests.get', Mock(side_effect=[response, response, requests.Timeout()]))
    articles, coverage, omitted, _, _ = collect(NOW, [('a','https://a.test'),('b','https://b.test'),('c','https://c.test')])
    assert len(articles) == 1 and omitted == 0
    assert [c['ok'] for c in coverage] == [True, True, False]


def test_all_sources_fail_not_empty_report(monkeypatch):
    monkeypatch.setattr('news.requests.get', Mock(side_effect=requests.Timeout()))
    with pytest.raises(ResearchError):
        collect(NOW, [('a','https://a.test')])


def test_html_is_not_successful_feed(monkeypatch):
    monkeypatch.setattr('news.requests.get', Mock(return_value=Mock(content=b'<html><body>denied</body></html>')))
    with pytest.raises(ResearchError):
        collect(NOW, [('a','https://a.test')])


def test_empty_feed_has_explicit_summary():
    overview, articles = summarize([])
    assert 'No se han encontrado' in overview and articles == []


def test_missing_key_does_not_fake_translation(monkeypatch):
    monkeypatch.delenv('NEWS_LLM_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(RuntimeError, match='Falta NEWS_LLM_API_KEY'):
        summarize([article()])


def test_translation_preserves_real_links_and_ids(monkeypatch):
    monkeypatch.setenv('NEWS_LLM_API_KEY','test-not-real')
    a = article()
    translated = {'overview':'Resumen en español', 'articles':[{'id':a['id'],'title_es':'Inversión','summary_es':'Noticia industrial','url':'https://invented.test'}]}
    response = Mock(ok=True)
    response.json.return_value = {'choices':[{'message':{'content':json.dumps(translated)}}]}
    monkeypatch.setattr('news.requests.post',Mock(return_value=response))
    overview, items = summarize([a])
    assert items[0]['url'] == a['url'] and overview == 'Resumen en español'
    translated['articles'][0]['id'] = 'invented'
    response.json.return_value = {'choices':[{'message':{'content':json.dumps(translated)}}]}
    with pytest.raises(RuntimeError, match='formato incompleto'):
        summarize([a])


def test_scheduler_madrid_dst():
    config = dict(enabled=True, time='08:00', timezone='Europe/Madrid')
    assert scheduled_day(config, datetime(2026,7,1,6,tzinfo=timezone.utc)) == '2026-07-01'
    assert scheduled_day(config, datetime(2026,10,26,6,tzinfo=timezone.utc)) is None
    assert scheduled_day(config, datetime(2026,10,26,7,tzinfo=timezone.utc)) == '2026-10-26'
    assert scheduled_day({**config,'enabled':False}, NOW) is None


def test_store_concurrency_recovery_and_persistence(tmp_path):
    store = Store(tmp_path)
    first = store.create_run('manual')
    assert first and store.create_run('manual') is None
    store.recover()
    assert store.get(first)['status'] == 'failed'
    second = store.create_run('automático','2026-10-26')
    store.finish(second, report())
    assert store.create_run('automático','2026-10-26') is None
    assert Store(tmp_path).get(second)['report']['overview'] == report()['overview']


def test_scheduled_executes_once_and_manual_again(tmp_path, monkeypatch):
    store = Store(tmp_path)
    worker = Worker(store)
    monkeypatch.setattr('worker.collect',lambda: ([article()],report()['coverage'],0,NOW-timedelta(days=1),NOW))
    monkeypatch.setattr('worker.summarize',lambda _, **kwargs: ('Resumen español',report()['articles']))
    monkeypatch.setattr(worker.executor,'submit',lambda fn, run_id: fn(run_id))
    first = worker.tick(NOW)
    assert store.get(first)['status'] == 'complete'
    assert worker.tick(NOW) is None
    second = worker.submit()
    assert store.get(second)['status'] == 'complete'
    worker.executor.shutdown()


def test_worker_reports_network_failures(tmp_path, monkeypatch):
    store = Store(tmp_path)
    worker = Worker(store)
    coverage = [{'name':'test','ok':False,'count':0,'message':'Falló'}]
    def fail():
        raise ResearchError('Ninguna fuente respondió', coverage)
    monkeypatch.setattr('worker.collect', fail)
    run_id = store.create_run('manual')
    worker.execute(run_id)
    run = store.get(run_id)
    assert run['status'] == 'failed' and run['report']['coverage'] == coverage
    worker.executor.shutdown()


def test_pdf_spanish_and_polish_text(tmp_path):
    r = report()
    r['articles'][0]['title'] = 'Łódź: wiadomości Boryszew'
    r['articles'][0]['summary_es'] = 'Inversión en España: información y análisis. <script>dato</script>'
    path = tmp_path/'report.pdf'
    path.write_bytes(build_pdf(r).getvalue())
    assert path.read_bytes().startswith(b'%PDF')
    text = subprocess.run(['pdftotext',str(path),'-'],capture_output=True,text=True,check=True).stdout
    assert 'Inversión en España' in text and 'Łódź' in text and 'Resumen del día' in text


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path)
    app.config['TESTING'] = True
    yield app
    app.extensions['worker'].executor.shutdown()


def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf']


def test_routes_settings_and_pdf(app):
    client = app.test_client()
    token = csrf(client)
    assert client.get('/').status_code == 200
    assert client.post('/generate').status_code == 400
    assert client.post('/generate',data={'csrf':'á'}).status_code == 400
    assert client.post('/settings',data={'csrf':token,'enabled':'on','time':'09:30','timezone':'Europe/Madrid'}).status_code == 303
    assert app.extensions['store'].settings()['time'] == '09:30'
    client.post('/settings',data={'csrf':token,'time':'99:99','timezone':'Invalid'})
    assert app.extensions['store'].settings()['time'] == '09:30'
    run_id = app.extensions['store'].create_run('manual')
    app.extensions['store'].finish(run_id, report())
    assert 'Resumen del día' in client.get('/').get_data(as_text=True)
    response = client.get(f'/reports/{run_id}/pdf?download=1')
    assert response.status_code == 200 and response.data.startswith(b'%PDF')
    assert 'attachment' in response.headers['Content-Disposition']
    assert client.get('/reports/999/pdf').status_code == 404


def test_manual_http_to_persisted_report_and_safe_html(app, monkeypatch):
    worker = app.extensions['worker']
    monkeypatch.setattr('worker.collect',lambda: ([article()],report()['coverage'],0,NOW-timedelta(days=1),NOW))
    monkeypatch.setattr('worker.summarize',lambda _, **kwargs: ('<script>alert(1)</script>',report()['articles']))
    monkeypatch.setattr(worker.executor,'submit',lambda fn, run_id: fn(run_id))
    client = app.test_client()
    assert client.post('/generate',data={'csrf':csrf(client)}).status_code == 303
    run = app.extensions['store'].history()[0]
    assert run['status'] == 'complete'
    html = client.get('/').get_data(as_text=True)
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<script>alert(1)</script>' not in html
    assert client.get(f"/reports/{run['id']}/pdf").status_code == 200


def test_single_service_lock_and_health(tmp_path, monkeypatch):
    monkeypatch.setattr('worker.Worker.start', lambda self: None)
    first = create_app(tmp_path, start_worker=True)
    first.extensions['worker'].stop.set()
    try:
        with pytest.raises(RuntimeError, match='Ya existe un servicio'):
            create_app(tmp_path, start_worker=True)
        response = first.test_client().get('/health').json
        assert response['application'] == 'boryszew-news' and response['scheduler'] is True
    finally:
        first.extensions['worker'].executor.shutdown()
        first.extensions['service_lock'].release()


def test_launcher_checks_application_identity(monkeypatch):
    import launch
    monkeypatch.setattr(launch.urllib.request, 'urlopen', lambda *a, **kw: BytesIO(b'{"status":"ok","application":"other"}'))
    assert launch.ready('http://example.test') is False
    monkeypatch.setattr(launch.urllib.request, 'urlopen', lambda *a, **kw: BytesIO(b'{"status":"ok","application":"boryszew-news"}'))
    assert launch.ready('http://example.test') is True


def test_download_package_excludes_private_files(tmp_path):
    from tools.package_app import package
    from zipfile import ZipFile
    target = package(tmp_path / 'app.zip')
    with ZipFile(target) as archive:
        names = archive.namelist()
        assert any(n.endswith('/launch.py') for n in names)
        assert any(n.endswith('/assets/fonts/DejaVuSans.ttf') for n in names)
        assert any(n.endswith('/assets/fonts/LICENSE.txt') for n in names)
        assert not any('/data/' in n or '/.venv/' in n or n.endswith('/.env') or '/__pycache__/' in n for n in names)


def test_local_key_is_not_echoed_and_can_be_removed(app, monkeypatch):
    monkeypatch.delenv('NEWS_LLM_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    client=app.test_client()
    token=csrf(client)
    secret='not-a-real-key-for-local-configuration-tests'
    assert client.post('/connection',data={'csrf':token,'api_key':secret}).status_code==303
    store=app.extensions['store']
    assert store.api_key()==secret
    html=client.get('/').get_data(as_text=True)
    assert secret not in html and 'Clave configurada' in html
    assert (store.directory/'llm.key').stat().st_mode & 0o777 == 0o600
    client.post('/connection',data={'csrf':token,'remove':'1'})
    assert store.api_key() is None
    client.post('/connection',data={'csrf':token,'api_key':'invalid'})
    assert store.api_key() is None
