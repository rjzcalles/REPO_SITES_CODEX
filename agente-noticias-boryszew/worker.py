import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from news import collect, summarize, ResearchError

log = logging.getLogger(__name__)


def scheduled_day(settings, now):
    if not settings['enabled']:
        return None
    local = now.astimezone(ZoneInfo(settings['timezone']))
    if local.strftime('%H:%M') < settings['time']:
        return None
    return local.date().isoformat()


class Worker:
    def __init__(self, store):
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='research')
        self.stop = threading.Event()

    def submit(self, trigger='manual', day=None):
        run_id = self.store.create_run(trigger, day)
        if run_id is not None:
            self.executor.submit(self.execute, run_id)
        return run_id

    def execute(self, run_id):
        try:
            articles, coverage, omitted, since, until = collect()
            overview, articles = summarize(articles, api_key=self.store.api_key())
            self.store.finish(run_id, dict(overview=overview, articles=articles, coverage=coverage,
                                          omitted=omitted, since=since.isoformat(), until=until.isoformat()))
        except ResearchError as exc:
            self.store.finish(run_id, report={'coverage': exc.coverage}, error=str(exc))
        except requests.RequestException:
            self.store.finish(run_id, error='Error de red o tiempo de espera al consultar la IA. Revisa la conectividad del proveedor.')
        except RuntimeError as exc:
            self.store.finish(run_id, error=str(exc))
        except Exception:
            log.error('Error inesperado en la ejecución %s; revisa configuración y disponibilidad del servicio.', run_id)
            self.store.finish(run_id, error='Error inesperado al generar el informe. Revisa la configuración del servicio.')

    def tick(self, now=None):
        day = scheduled_day(self.store.settings(), now or datetime.now(timezone.utc))
        if day and not self.store.scheduled(day):
            return self.submit('automático', day)
        return None

    def start(self):
        def loop():
            while not self.stop.is_set():
                try:
                    self.tick()
                except Exception:
                    log.error('No se pudo comprobar la programación diaria.')
                self.stop.wait(20)
        threading.Thread(target=loop, name='daily-scheduler', daemon=True).start()
