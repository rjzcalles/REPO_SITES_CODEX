import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'news.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY, created TEXT NOT NULL, trigger TEXT NOT NULL,
                    status TEXT NOT NULL, error TEXT, report TEXT, scheduled_day TEXT UNIQUE);
                CREATE UNIQUE INDEX IF NOT EXISTS one_running ON runs(status) WHERE status='running';
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES (1, ?)',
                       (json.dumps(dict(enabled=True, time='08:00', timezone='Europe/Madrid')),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        with self.connect() as db:
            return json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])

    def api_key(self):
        path = self.directory / 'llm.key'
        return path.read_text().strip() if path.exists() else None

    def save_api_key(self, value):
        path = self.directory / 'llm.key'
        if not value:
            path.unlink(missing_ok=True)
            return
        temporary = self.directory / ('key-' + secrets.token_hex(8) + '.tmp')
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as file:
                file.write(value)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def save_settings(self, value):
        with self.connect() as db:
            db.execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(value),))

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='failed', error='La ejecución se interrumpió al reiniciar el servicio. Puedes generar otro informe.' WHERE status='running'")

    def create_run(self, trigger, scheduled_day=None):
        with self.connect() as db:
            try:
                cursor = db.execute("INSERT INTO runs(created, trigger, status, scheduled_day) VALUES (?, ?, 'running', ?)",
                                    (datetime.now(timezone.utc).isoformat(), trigger, scheduled_day))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None

    def finish(self, run_id, report=None, error=None):
        with self.connect() as db:
            db.execute('UPDATE runs SET status=?, report=?, error=? WHERE id=?',
                       ('failed' if error else 'complete', json.dumps(report, ensure_ascii=False) if report is not None else None, error, run_id))

    @staticmethod
    def decode(row):
        if row is None:
            return None
        result = dict(row)
        result['report'] = json.loads(result['report']) if result['report'] else None
        return result

    def get(self, run_id):
        with self.connect() as db:
            return self.decode(db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone())

    def history(self):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 60')]

    def scheduled(self, day):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM runs WHERE scheduled_day=?', (day,)).fetchone() is not None
