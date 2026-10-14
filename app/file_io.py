"""💾 Write complete JSON and file copies before replacing saved data."""
import json
import os
import tempfile
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def _atomic_file(path, mode):
    target = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=target.name + '.', suffix='.tmp', dir=target.parent)
    try:
        options = {'encoding': 'utf-8'} if mode == 'w' else {}
        with os.fdopen(fd, mode, **options) as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def atomic_write_json(path, data):
    with _atomic_file(path, 'w') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)


def atomic_write_bytes(path, payload):
    with _atomic_file(path, 'wb') as stream:
        stream.write(payload)
