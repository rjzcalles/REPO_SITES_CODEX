"""Crea un paquete explícito de código, sin datos de usuario ni credenciales."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    'app.py', 'launch.py', 'news.py', 'reports.py', 'store.py', 'worker.py',
    'iniciar.bat', 'iniciar.command', 'README.md', 'LEEME-PRIMERO.txt', 'AGENTS.md', '.env.example',
    'requirements.txt', 'requirements-dev.txt', 'requirements.lock', '.gitignore',
]
DIRECTORIES = ['templates', 'static', 'assets/fonts', 'tests', 'tools', 'docs']


def package(destination=None):
    target = destination or ROOT / 'dist' / 'observatorio-boryszew.zip'
    target.parent.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / name for name in FILES]
    for name in DIRECTORIES:
        paths.extend(p for p in (ROOT / name).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    with ZipFile(target, 'w', compression=ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            if path.is_symlink():
                raise ValueError(f'No se incluyen enlaces simbólicos: {path.name}')
            archive.write(path, Path(ROOT.name) / path.relative_to(ROOT))
    return target


if __name__ == '__main__':
    print(package())
