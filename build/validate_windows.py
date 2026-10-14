"""✅ Check upgrade, install, repair, and removal."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from build_utils import app_version

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description='Check the real Windows installer on a clean machine')
    parser.add_argument('--previous-installer', type=Path)
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise RuntimeError('Installer checks need Windows.')
    output = ROOT / 'build' / 'output'; output.mkdir(parents=True, exist_ok=True)
    installer = ROOT / 'dist_installer' / f'WhiteBoard-{app_version()}-x64.msi'
    installed = Path(os.environ['ProgramFiles']) / 'WhiteBoard'
    built = ROOT / 'dist' / 'WhiteBoard'
    if installed.exists():
        raise RuntimeError('Use a clean Windows test machine. WhiteBoard is already installed here.')
    previous = args.previous_installer
    if previous and digest(previous) != 'e1cfd844f53e39d05cd32090ecf0d24e33d8da86c321eef7e8ab33bcdf1dc71c':
        raise RuntimeError('The previous MSI does not match the published 1.0.0 checksum.')

    def msi(action, name, target=installer, cleanup=False):
        result = subprocess.run(['msiexec', action, str(target), '/qn', '/norestart', '/l*v', str(output / f'{name}.log')], timeout=180)
        accepted = (0, 3010, 1605) if cleanup else (0, 3010)
        if result.returncode not in accepted:
            raise RuntimeError(f'{name} failed with MSI exit code {result.returncode}. Read build/output/{name}.log.')

    def launch(environment):
        subprocess.run([str(installed / 'WhiteBoard.exe'), '--smoke-test'], env=environment, timeout=45, check=True)

    attempted_install = False
    try:
        with tempfile.TemporaryDirectory(prefix='whiteboard-install-test-') as temporary:
            data = Path(temporary)
            environment = dict(os.environ, WHITEBOARD_DATA_DIR=str(data))
            if previous:
                attempted_install = True
                msi('/i', 'install-previous', previous); launch(environment)
                legacy = next((data / 'projects').glob('*.json'))
                project = json.loads(legacy.read_text(encoding='utf-8'))
                project['cards'] = [{'id': 'upgrade-check', 'title': 'Existing task', 'description': 'Keep this data',
                    'card_type': 'Fix', 'priority': 'P1', 'column_id': project['columns'][0]['id'],
                    'order': 0, 'created_at': 1700000000, 'updated_at': 1700000000}]
                legacy.write_text(json.dumps(project, indent=2), encoding='utf-8')
                before_project = legacy.read_bytes()
                index = data / 'index.json'
                settings = json.loads(index.read_text(encoding='utf-8'))
                settings['settings']['ui_font'] = 'Arial'; settings['settings']['ui_scale'] = 125
                index.write_text(json.dumps(settings, indent=2), encoding='utf-8')
                before_index = index.read_bytes()
            attempted_install = True
            msi('/i', 'upgrade' if previous else 'install')
            assert (installed / 'WhiteBoard.exe').is_file(), 'Installer did not create WhiteBoard.exe'
            launch(environment)
            index = data / 'index.json'; assert index.is_file(), 'Installed app did not create local data'
            if previous:
                assert index.read_bytes() == before_index, 'Upgrade changed settings'
                assert legacy.read_bytes() == before_project, 'Upgrade changed project data'
            before = index.read_bytes()
            (installed / 'WhiteBoard.exe').unlink()
            msi('/fa', 'repair')
            for file in built.rglob('*'):
                if file.is_file():
                    assert digest(file) == digest(installed / file.relative_to(built)), f'Repair did not restore {file.name}'
            assert index.read_bytes() == before, 'Repair changed user data'
            launch(environment)
            msi('/x', 'uninstall')
            assert not (installed / 'WhiteBoard.exe').exists(), 'Uninstall left the executable behind'
            assert index.is_file() and index.read_bytes() == before, 'Uninstall changed user data'
            if previous:
                assert legacy.read_bytes() == before_project, 'Repair or uninstall changed project data'
        (output / 'windows-validation.txt').write_text('✅ ' + ('Verified 1.0.0 upgrade, existing tasks and settings, ' if previous else 'Install, ') + 'installed-app launch, full file repair, second launch, uninstall, and user-data preservation passed.\n', encoding='utf-8')
    finally:
        if attempted_install and installed.exists():
            msi('/x', 'cleanup-current', cleanup=True)
            if previous:
                msi('/x', 'cleanup-previous', previous, cleanup=True)


if __name__ == '__main__':
    main()
