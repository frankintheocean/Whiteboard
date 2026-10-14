"""🔧 Build WhiteBoard and its Windows installer without batch files."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from build_utils import use_utf8_console

ROOT = Path(__file__).resolve().parents[1]
NS = 'http://wixtoolset.org/schemas/v4/wxs'


def run(*args):
    environment = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT / 'build' / 'work' / 'cache'))
    subprocess.run([str(a) for a in args], cwd=ROOT, env=environment, check=True)


def build_installer():
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise RuntimeError('The Windows x64 installer must be built on Windows x64.')
    wix = shutil.which('wix')
    if not wix:
        raise RuntimeError('Install WiX 5.0.2 with dotnet tool install --global wix --version 5.0.2.')
    app = ROOT / 'dist' / 'WhiteBoard'
    if not (app / 'WhiteBoard.exe').is_file():
        raise RuntimeError('Build WhiteBoard.exe before making the installer.')
    ET.register_namespace('', NS)
    document = ET.Element(f'{{{NS}}}Wix')
    fragment = ET.SubElement(document, 'Fragment')
    install_dir = ET.SubElement(fragment, 'DirectoryRef', Id='INSTALLFOLDER')
    group = ET.SubElement(fragment, 'ComponentGroup', Id='AppFiles')
    directories = {Path('.'): install_dir}
    for file in sorted(p for p in app.rglob('*') if p.is_file()):
        relative = file.relative_to(app)
        current = Path('.')
        for part in relative.parent.parts:
            current = current / part
            if current not in directories:
                identifier = 'D' + hashlib.sha256(current.as_posix().encode()).hexdigest()[:24]
                directories[current] = ET.SubElement(directories[current.parent], 'Directory', Id=identifier, Name=part)
        token = hashlib.sha256(relative.as_posix().encode()).hexdigest()[:24]
        component = ET.SubElement(directories[relative.parent], 'Component', Id='C' + token, Guid='*', Bitness='always64')
        ET.SubElement(component, 'File', Id='F' + token, Source=str(file), KeyPath='yes')
        ET.SubElement(group, 'ComponentRef', Id='C' + token)
    work = ROOT / 'build' / 'work'
    work.mkdir(parents=True, exist_ok=True)
    files_path = work / 'files.wxs'
    ET.indent(document)
    ET.ElementTree(document).write(files_path, encoding='utf-8', xml_declaration=True)
    license_text = (ROOT / 'LICENSE').read_text(encoding='utf-8')
    escaped = license_text.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}').replace('\n', '\\par\n')
    (work / 'license.rtf').write_text('{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Segoe UI;}}\\f0\\fs18\n' + escaped + '}', encoding='utf-8')
    output = ROOT / 'dist_installer' / 'WhiteBoard-1.0.0-x64.msi'
    output.parent.mkdir(exist_ok=True)
    run(wix, 'build', '-arch', 'x64', '-ext', 'WixToolset.UI.wixext/5.0.2',
        '-d', f'ProjectRoot={ROOT}', ROOT / 'build' / 'installer.wxs', files_path, '-o', output)
    print(f'📦 Installer: {output}')


def main():
    use_utf8_console()
    parser = argparse.ArgumentParser(description='🏗️ Build WhiteBoard 1.0.0')
    parser.add_argument('--installer', action='store_true', help='Build the Windows x64 MSI too')
    args = parser.parse_args()
    if args.installer and (sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64')):
        parser.error('Build the Windows x64 installer on Windows x64.')
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--workpath',
        ROOT / 'build' / 'work' / 'pyinstaller', '--distpath', ROOT / 'dist', ROOT / 'build' / 'whiteboard.spec')
    if args.installer:
        build_installer()


if __name__ == '__main__':
    main()
