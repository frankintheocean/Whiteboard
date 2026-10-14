"""⚖️ Include the licenses shipped with the installed build packages."""
import importlib.metadata
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'build' / 'output' / 'third-party-licenses'
TARGET.mkdir(parents=True, exist_ok=True)
for name in ('PySide6-Essentials', 'shiboken6', 'pyinstaller'):
    dist = importlib.metadata.distribution(name)
    for file in dist.files or []:
        if any(part.lower().startswith(('license', 'copying')) for part in file.parts):
            source = Path(dist.locate_file(file))
            if source.is_file():
                target = TARGET / name / str(file)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    (TARGET / f'{name}-version.txt').write_text(f'📚 {name} {dist.version}\n', encoding='utf-8')
