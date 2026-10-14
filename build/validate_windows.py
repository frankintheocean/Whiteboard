"""✅ Test the real MSI: install, start, repair, and uninstall."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if sys.platform != 'win32':
        raise RuntimeError('Installer checks need Windows.')
    output = ROOT / 'build' / 'output'
    output.mkdir(parents=True, exist_ok=True)
    installer = ROOT / 'dist_installer' / 'WhiteBoard-1.0.0-x64.msi'
    installed = Path(os.environ['ProgramFiles']) / 'WhiteBoard'
    built = ROOT / 'dist' / 'WhiteBoard'
    if installed.exists():
        raise RuntimeError('Use a clean Windows test machine. WhiteBoard is already installed here.')

    def msi(action, name, *extra):
        result = subprocess.run(['msiexec', action, str(installer), '/qn', '/norestart', '/l*v', str(output / f'{name}.log'), *extra], timeout=180)
        if result.returncode not in (0, 3010):
            raise RuntimeError(f'{name} failed with MSI exit code {result.returncode}. Read build/output/{name}.log.')

    installed_ok = False
    try:
        msi('/i', 'install')
        installed_ok = True
        assert (installed / 'WhiteBoard.exe').is_file(), 'Installer did not create WhiteBoard.exe'
        with tempfile.TemporaryDirectory(prefix='whiteboard-install-test-') as temporary:
            data = Path(temporary)
            env = dict(os.environ, WHITEBOARD_DATA_DIR=str(data))
            subprocess.run([str(installed / 'WhiteBoard.exe'), '--smoke-test'], env=env, timeout=45, check=True)
            index = data / 'index.json'
            assert index.is_file(), 'Installed app did not create its local data'
            before = index.read_bytes()
            (installed / 'WhiteBoard.exe').unlink()
            msi('/fa', 'repair')
            for file in built.rglob('*'):
                if file.is_file():
                    assert digest(file) == digest(installed / file.relative_to(built)), f'Repair did not restore {file.name}'
            assert index.read_bytes() == before, 'Repair changed user data'
            subprocess.run([str(installed / 'WhiteBoard.exe'), '--smoke-test'], env=env, timeout=45, check=True)
            msi('/x', 'uninstall')
            installed_ok = False
            assert not (installed / 'WhiteBoard.exe').exists(), 'Uninstall left the executable behind'
            assert index.is_file() and index.read_bytes() == before, 'Uninstall changed user data'
        (output / 'windows-validation.txt').write_text('✅ Install, installed-app launch, full file repair, second launch, uninstall, and user-data preservation passed.\n', encoding='utf-8')
    finally:
        if installed_ok:
            msi('/x', 'cleanup')


if __name__ == '__main__':
    main()
