"""🩺 Keep a small local error log."""
import os
import time
import traceback
from typing import List, Optional

# Cap the in-memory buffer and the on-disk file independently: the buffer
# only needs to hold enough for the Diagnostics tab to show something
# useful at a glance, while the file is allowed to hold more history
# since it's just appended text, not something rendered into a widget
# every time it changes.
MAX_MEMORY_ENTRIES = 50
MAX_LOG_FILE_BYTES = 512 * 1024  # 512KB -- trimmed from the front when exceeded

_entries: List[str] = []
_log_path: Optional[str] = None


def init(data_dir: str):
    """Point the logger at the app's data directory. Called once from
    main.py right after Storage() resolves that path -- before this is
    called, log_error() below still works (appends to the in-memory
    buffer), it just can't write to disk yet, so an exception raised
    during Storage() construction itself is never lost even though it
    happens before init() can run."""
    global _log_path
    try:
        os.makedirs(data_dir, exist_ok=True)
        _log_path = os.path.join(data_dir, "error.log")
    except OSError:
        # No writable data dir (unusual, but not fatal): logging simply
        # stays in-memory-only for this session rather than raising here,
        # since this runs during startup before any UI exists to show an
        # error about the error logger itself.
        _log_path = None


def log_error(context: str, exc: BaseException = None):
    """Record one error. context: a short human-readable description of
    what was happening (e.g. "Save project", "Open file") -- not a full
    sentence, just enough to tell entries apart in the Diagnostics list.
    exc: the exception, if any (also accepts None for a bare message).
    Never raises: a failure here must never mask or replace whatever
    error triggered the call in the first place."""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        if exc is not None:
            detail = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).strip()
        else:
            detail = ""
        entry = f"[{timestamp}] {context}" + (f"\n{detail}" if detail else "")
        _entries.append(entry)
        if len(_entries) > MAX_MEMORY_ENTRIES:
            del _entries[: len(_entries) - MAX_MEMORY_ENTRIES]
        _append_to_file(entry)
    except Exception:
        # Logging must never itself crash the app or the caller's own
        # except block -- silently drop if anything above went wrong.
        pass


def _append_to_file(entry: str):
    if _log_path is None:
        return
    try:
        # Trim the file from the front once it grows past the cap, so a
        # long-running session's log can't grow without bound. Cheap
        # relative to how rarely errors actually occur -- this reads the
        # whole (already size-capped) file only when a new error is being
        # appended, not on every save/load like the rest of the app's
        # normal-path I/O.
        existing = ""
        if os.path.exists(_log_path):
            try:
                with open(_log_path, "r", encoding="utf-8") as f:
                    existing = f.read()
            except OSError:
                existing = ""
        combined = existing + ("\n\n" if existing else "") + entry
        if len(combined.encode("utf-8", errors="ignore")) > MAX_LOG_FILE_BYTES:
            combined = combined[-MAX_LOG_FILE_BYTES:]
        tmp_path = _log_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(combined)
        os.replace(tmp_path, _log_path)
    except OSError:
        pass


def recent_entries() -> List[str]:
    """Most-recent-first list of in-memory entries, for Diagnostics."""
    return list(reversed(_entries))


def entry_count() -> int:
    return len(_entries)


def clear():
    """Clear the in-memory buffer and truncate the on-disk file. Used by
    Diagnostics' \"Clear Log\" action. Best-effort like everything else
    here -- if the file can't be truncated, the in-memory buffer is still
    cleared so the visible list empties either way."""
    _entries.clear()
    if _log_path is not None:
        try:
            with open(_log_path, "w", encoding="utf-8"):
                pass
        except OSError:
            pass
