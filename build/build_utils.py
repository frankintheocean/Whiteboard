"""🌐 Print readable Windows build messages."""
import sys


def use_utf8_console():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')


def app_version():
    import ast
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / 'app' / 'app_meta.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'APP_VERSION' for t in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value):
                return value
    raise ValueError('The app version must have three numbers, such as 1.1.0.')


def windows_version_file(root):
    version = app_version()
    template = (root / 'build' / 'version_info.txt').read_text(encoding='utf-8')
    content = template.replace('@VERSION@', version).replace('@NUMERIC@', ','.join(version.split('.')) + ',0')
    target = root / 'build' / 'work' / 'version_info.txt'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
    return str(target)
