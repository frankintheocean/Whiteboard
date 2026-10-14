"""📎 Store verified file copies and include them in project exports."""
import base64
import hashlib
import os
from pathlib import Path
import re
from file_io import atomic_write_bytes

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_PROJECT_BYTES = 100 * 1024 * 1024
BLOCKED_SUFFIXES = {'.exe', '.com', '.bat', '.cmd', '.ps1', '.vbs', '.vbe', '.js', '.jse', '.msi', '.msp', '.dll', '.lnk', '.url', '.hta', '.scr', '.reg', '.desktop', '.sh', '.py', '.pyw', '.jar', '.msc', '.application', '.appref-ms', '.xll'}


def file_name(value):
    if not isinstance(value, str) or not value or len(value) > 180:
        raise ValueError('Use a file name with 1–180 characters.')
    if value.endswith((' ', '.')) or value.split('.')[0].casefold() in {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}:
        raise ValueError('Use a regular Windows file name.')
    if any(c in value for c in '/\\:\x00<>|"*?') or value in ('.', '..') or any(ord(c) < 32 for c in value):
        raise ValueError('An attachment name cannot contain paths or control characters.')
    if Path(value).suffix.lower() in BLOCKED_SUFFIXES:
        raise ValueError('Executable files and shortcuts cannot be attached. Use a document or image instead.')
    return value


def clean_attachments(value):
    if not isinstance(value, list):
        raise ValueError('Attachments must be a list.')
    result, seen = [], set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('Each attachment must be an object.')
        name = file_name(item.get('name'))
        digest = item.get('sha256', '')
        size = item.get('size')
        if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('An attachment has an invalid checksum.')
        if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= MAX_FILE_BYTES:
            raise ValueError('Each attachment must be 25 MB or smaller.')
        key = (digest, name)
        if key in seen:
            continue
        seen.add(key)
        entry = {'name': name, 'sha256': digest, 'size': size}
        if 'data' in item:
            data = item['data']
            if not isinstance(data, str) or len(data) > ((MAX_FILE_BYTES + 2) // 3) * 4:
                raise ValueError('An embedded attachment is too large or invalid.')
            entry['data'] = data
        result.append(entry)
    if sum({a['sha256']: a['size'] for a in result}.values()) > MAX_PROJECT_BYTES:
        raise ValueError('Attachments must total 100 MB or less per project.')
    return result


def project_file_bytes(project, exclude_card=None):
    files = {a['sha256']: a['size'] for c in project.cards if c.id != exclude_card for a in c.attachments}
    return sum(files.values())


class AttachmentStore:
    def __init__(self, data_dir):
        self.root = Path(data_dir) / 'attachments'
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, entry):
        entry = clean_attachments([entry])[0]
        suffix = Path(entry['name']).suffix.lower()
        path = self.root / (entry['sha256'] + suffix)
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('The attachment path is outside local storage.')
        return path

    def _write(self, entry, payload):
        if len(payload) != entry['size'] or hashlib.sha256(payload).hexdigest() != entry['sha256']:
            raise ValueError('The attachment checksum or size does not match.')
        path = self.path(entry)
        if path.exists():
            try:
                if self.read(entry) == payload:
                    return entry
            except (OSError, ValueError):
                pass
        atomic_write_bytes(path, payload)
        return entry

    def add(self, source):
        source = Path(source)
        name = file_name(source.name)
        with source.open('rb') as stream:
            payload = stream.read(MAX_FILE_BYTES + 1)
        if len(payload) > MAX_FILE_BYTES:
            raise ValueError('Each attachment must be 25 MB or smaller.')
        entry = {'name': name, 'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
        return self._write(entry, payload)

    def read(self, entry):
        with self.path(entry).open('rb') as stream:
            payload = stream.read(MAX_FILE_BYTES + 1)
        if len(payload) != entry['size'] or hashlib.sha256(payload).hexdigest() != entry['sha256']:
            raise ValueError('The saved attachment changed or is damaged. Import a fresh copy.')
        return payload

    def import_project(self, project, bundle=None):
        total = project_file_bytes(project)
        if total > MAX_PROJECT_BYTES:
            raise ValueError('Attachments must total 100 MB or less per project.')
        decoded = []
        cache = {}
        bundle = bundle if isinstance(bundle, dict) else {}
        for card in project.cards:
            for entry in card.attachments:
                encoded = entry.get('data', bundle.get(entry['sha256']))
                if encoded is not None:
                    if not isinstance(encoded, str) or len(encoded) > ((MAX_FILE_BYTES + 2) // 3) * 4:
                        raise ValueError('An embedded attachment is too large or invalid.')
                    try:
                        key = entry['sha256']
                        if key not in cache:
                            cache[key] = base64.b64decode(encoded, validate=True)
                        payload = cache[key]
                    except (ValueError, TypeError) as error:
                        raise ValueError('An embedded attachment is not valid base64.') from error
                    if len(payload) != entry['size'] or hashlib.sha256(payload).hexdigest() != entry['sha256']:
                        raise ValueError('An embedded attachment failed its checksum check.')
                    decoded.append((entry, payload))
                else:
                    try:
                        self.read(entry)
                    except (OSError, ValueError) as error:
                        raise ValueError("This project is missing an attachment. Export it again with its files.") from error
        # Validate the whole import before writing any file.
        written = set()
        for entry, payload in decoded:
            path = self.path(entry)
            if path not in written:
                self._write(entry, payload)
                written.add(path)
        for card in project.cards:
            for entry in card.attachments:
                entry.pop('data', None)

    def export_project(self, project):
        total = project_file_bytes(project)
        if total > MAX_PROJECT_BYTES:
            raise ValueError('Attachments must total 100 MB or less per project.')
        data = project.to_dict()
        bundle = {}
        for card in data['cards']:
            for entry in card['attachments']:
                if entry['sha256'] not in bundle:
                    bundle[entry['sha256']] = base64.b64encode(self.read(entry)).decode('ascii')
        if bundle:
            data['attachment_files'] = bundle
        return data

    def open_copy(self, entry):
        # Opening a copy keeps the saved attachment unchanged by other apps.
        payload = self.read(entry)
        folder = self.root / 'opened'
        folder.mkdir(exist_ok=True)
        if not folder.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('The attachment preview folder is unsafe.')
        target = folder / (entry['sha256'][:12] + '-' + file_name(entry['name']))
        if target.is_symlink():
            raise ValueError('The attachment preview path is unsafe.')
        atomic_write_bytes(target, payload)
        return target
