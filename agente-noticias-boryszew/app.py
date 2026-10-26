import hmac
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from filelock import FileLock, Timeout
from news import QUERIES
from reports import LIMITATION, build_pdf
from store import Store
from worker import Worker

ROOT = Path(__file__).resolve().parent


def create_app(data_dir=None, start_worker=False):
    app = Flask(__name__)
    store = Store(data_dir or os.getenv('NEWS_DATA_DIR', str(ROOT / 'data')))
    secret_path = store.directory / 'session.key'
    try:
        fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, 'w') as file:
            file.write(secrets.token_hex(32))
    app.secret_key = secret_path.read_text().strip()
    app.config.update(MAX_CONTENT_LENGTH=16_384, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax')
    worker = Worker(store)
    app.extensions.update(store=store, worker=worker)
    if start_worker:
        lock = FileLock(store.directory / 'service.lock')
        try:
            lock.acquire(timeout=0)
        except Timeout:
            raise RuntimeError('Ya existe un servicio activo con este directorio de datos.') from None
        app.extensions['service_lock'] = lock
        store.recover()
        worker.start()

    @app.before_request
    def protect_forms():
        session.setdefault('csrf', secrets.token_urlsafe(32))
        if request.method == 'POST' and not hmac.compare_digest(session['csrf'].encode(), request.form.get('csrf', '').encode()):
            abort(400, 'Formulario caducado. Recarga la página.')

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.template_filter('localdate')
    def localdate(value):
        return datetime.fromisoformat(value).astimezone(ZoneInfo(store.settings()['timezone'])).strftime('%d/%m/%Y · %H:%M')

    @app.context_processor
    def common():
        return dict(limitation=LIMITATION)

    @app.get('/')
    def index():
        history = store.history()
        running = next((run for run in history if run['status'] == 'running'), None)
        selected = None
        if request.args.get('report', '').isdigit():
            selected = store.get(int(request.args['report']))
        if selected is None:
            selected = next((run for run in history if run['status'] != 'running'), None)
        return render_template('index.html', history=history, selected=selected, running=running,
                               settings=store.settings(),
                               source_count=len(QUERIES) + sum(bool(url.strip()) for url in os.getenv('NEWS_RSS_URLS', '').split(',')),
                               environment_key=bool(os.getenv('NEWS_LLM_API_KEY') or os.getenv('OPENAI_API_KEY')),
                               configured=bool(os.getenv('NEWS_LLM_API_KEY') or os.getenv('OPENAI_API_KEY') or store.api_key()))

    @app.post('/generate')
    def generate():
        run_id = worker.submit()
        flash('Investigación iniciada. El informe aparecerá al terminar.' if run_id else 'Ya hay una investigación en curso.')
        return redirect(url_for('index'), code=303)

    @app.post('/settings')
    def settings():
        time = request.form.get('time', '')
        zone = request.form.get('timezone', '')
        try:
            if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', time):
                raise ValueError()
            ZoneInfo(zone)
        except (ValueError, ZoneInfoNotFoundError):
            flash('Indica una hora válida y una zona horaria reconocida, por ejemplo Europe/Madrid.')
            return redirect(url_for('index'), code=303)
        store.save_settings(dict(enabled=request.form.get('enabled') == 'on', time=time, timezone=zone))
        flash('Programación guardada.')
        return redirect(url_for('index'), code=303)

    @app.post('/connection')
    def connection():
        if request.form.get('remove') == '1':
            store.save_api_key(None)
            flash('Clave local eliminada.')
        elif os.getenv('NEWS_LLM_API_KEY') or os.getenv('OPENAI_API_KEY'):
            flash('La clave está gestionada por el entorno. Modifícala en su configuración.')
        else:
            key = request.form.get('api_key', '').strip()
            if not 20 <= len(key) <= 512 or not key.isascii() or any(c.isspace() for c in key):
                flash('La clave no tiene un formato válido. Revisa el valor sin compartirlo en el chat.')
            else:
                store.save_api_key(key)
                flash('Clave guardada en este ordenador. Genera un informe para utilizar la conexión.')
        return redirect(url_for('index', _anchor='conexion'), code=303)

    @app.get('/reports/<int:run_id>/pdf')
    def pdf(run_id):
        run = store.get(run_id)
        if run is None or run['status'] != 'complete':
            abort(404)
        return send_file(build_pdf(run['report']), mimetype='application/pdf',
                         as_attachment=request.args.get('download') == '1',
                         download_name=f'boryszew-informe-{run_id}.pdf')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'scheduler': start_worker, 'application': 'boryszew-news'}

    return app


if __name__ == '__main__':
    from waitress import serve
    serve(create_app(start_worker=True), host=os.getenv('NEWS_HOST', '127.0.0.1'),
          port=int(os.getenv('PORT', '8000')), threads=4)
