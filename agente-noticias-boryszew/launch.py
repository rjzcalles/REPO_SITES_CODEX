"""Arranque local: prepara dependencias, inicia el servidor y abre el navegador."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def ready(url):
    try:
        with urllib.request.urlopen(url + '/health', timeout=2) as response:
            result = json.load(response)
            return result.get('application') == 'boryszew-news' and result.get('status') == 'ok'
    except (OSError, ValueError):
        return False


def main():
    if sys.version_info < (3, 12):
        raise SystemExit('Instala Python 3.12 o posterior antes de iniciar la aplicación.')
    port = int(os.getenv('PORT', '8000'))
    url = f'http://127.0.0.1:{port}'
    if ready(url):
        print('La aplicación ya está abierta. Abriendo el navegador…')
        webbrowser.open(url)
        return
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('Preparando el entorno local…', flush=True)
        venv.EnvBuilder(with_pip=True).create(ROOT / '.venv')
    print('Comprobando dependencias…', flush=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.lock')], cwd=ROOT, check=True)
    print('Iniciando el observatorio. Mantén esta ventana abierta.', flush=True)
    process = subprocess.Popen([str(python), str(ROOT / 'app.py')], cwd=ROOT,
                               env={**os.environ, 'NEWS_HOST': '127.0.0.1'})
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError('El servicio no pudo arrancar. Revisa el mensaje anterior y si el puerto está ocupado.')
            if ready(url):
                print('Observatorio listo. Abriendo el navegador…', flush=True)
                if not webbrowser.open(url):
                    print(f'No se pudo abrir el navegador automáticamente. El servicio local está en el puerto {port}.')
                process.wait()
                return
            time.sleep(.25)
        raise RuntimeError('El servicio no respondió a tiempo.')
    except KeyboardInterrupt:
        print('\nCerrando el observatorio…')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f'No se pudo iniciar la aplicación: {exc}', file=sys.stderr)
        raise SystemExit(1)
