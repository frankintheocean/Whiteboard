# 🏗️ List app files for the standalone build.
# 🏗️ Build the app folder. Run from the project root.
from pathlib import Path
import sys
sys.path.insert(0, SPECPATH)
from build_utils import windows_version_file

root = Path(SPECPATH).parent
app_path = root / 'app'
assets = root / 'build' / 'assets'

a = Analysis(
    [str(app_path / 'main.py')], pathex=[str(app_path)],
    binaries=[], datas=[(str(assets / 'whiteboard.ico'), 'build/assets')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtNetwork', 'PySide6.QtMultimedia', 'PySide6.QtWebEngineCore'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='WhiteBoard',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(assets / 'whiteboard.ico'),
    version=windows_version_file(root) if sys.platform == 'win32' else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='WhiteBoard')
