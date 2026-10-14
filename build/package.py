"""🎁 Bundle source and release files in one ZIP."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import shutil
import zipfile

from build_utils import use_utf8_console

ROOT = Path(__file__).resolve().parents[1]
NAME = 'WhiteBoard-1.0.0'


def tracked_sources():
    if (ROOT / '.git').exists():
        result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, capture_output=True)
        return [ROOT / name for name in result.stdout.decode().split('\0') if name]
    # An extracted release has no Git metadata. Include source folders only.
    excluded = {'__pycache__', '.pytest_cache', 'work', 'output'}
    root_files = {'README.md', 'CHANGELOG.md', 'LICENSE', 'pytest.ini', 'requirements-dev.lock', '.gitignore'}
    files = [p for p in ROOT.iterdir() if p.is_file() and p.name in root_files]
    for name in ('app', 'build', 'tests', 'docs', '.github'):
        for path in (ROOT / name).rglob('*'):
            if path.is_file() and not any(part in excluded for part in path.relative_to(ROOT).parts):
                files.append(path)
    return files


def main():
    use_utf8_console()
    parser = argparse.ArgumentParser(description='🎁 Package the full WhiteBoard release')
    parser.add_argument('--installer', action='store_true', help='Require and include the Windows MSI and app')
    args = parser.parse_args()
    output = ROOT / 'artifacts'
    output.mkdir(exist_ok=True)
    suffix = 'complete' if args.installer else 'source'
    archive = output / f'{NAME}-{suffix}.zip'
    files = [(p, p.relative_to(ROOT)) for p in tracked_sources() if p.is_file()]
    if args.installer:
        installer = ROOT / 'dist_installer' / 'WhiteBoard-1.0.0-x64.msi'
        executable = ROOT / 'dist' / 'WhiteBoard' / 'WhiteBoard.exe'
        if not installer.is_file() or not executable.is_file():
            raise RuntimeError('The complete release needs a built Windows installer and app.')
        files += [(p, Path('application') / p.relative_to(ROOT / 'dist')) for p in (ROOT / 'dist' / 'WhiteBoard').rglob('*') if p.is_file()]
        files.append((installer, Path('installer') / installer.name))
        # Qt licenses and SBOM come from the actual build dependencies.
        licenses = ROOT / 'build' / 'output'
        if licenses.exists():
            files += [(p, Path('licenses') / p.relative_to(licenses)) for p in licenses.rglob('*') if p.is_file()]
    manifest = []
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for file, relative in sorted(files, key=lambda pair: pair[1].as_posix()):
            content = file.read_bytes()
            z.writestr(f'{NAME}/{relative.as_posix()}', content)
            manifest.append(f'{hashlib.sha256(content).hexdigest()}  {relative.as_posix()}')
        z.writestr(f'{NAME}/SHA256SUMS.txt', '\n'.join(manifest) + '\n')
    checksum = output / 'SHA256SUMS.txt'
    sums = [f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}']
    if args.installer:
        target = output / installer.name
        shutil.copy2(installer, target)
        sums.append(f'{hashlib.sha256(target.read_bytes()).hexdigest()}  {target.name}')
    checksum.write_text('\n'.join(sums) + '\n', encoding='utf-8')
    print(f'🎁 Release ZIP: {archive}')


if __name__ == '__main__':
    main()
