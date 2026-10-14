"""🗃️ Keep projects and settings on disk."""
import hashlib
import json
import os
import sys
import copy
from file_io import atomic_write_json
from typing import Dict, List, Optional

from models import Project, CARD_TYPES
from attachments import AttachmentStore


def get_data_dir() -> str:
    override = os.environ.get("WHITEBOARD_DATA_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return os.path.abspath(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        path = os.path.join(base, "WhiteBoard")
    else:
        path = os.path.join(os.path.expanduser("~"), ".whiteboard")
    os.makedirs(path, exist_ok=True)
    return path


DEFAULT_SETTINGS = {
    "theme": "macos_light",
    "confirm_deletes": True,
    "card_numbering": True,
    "custom_card_types": [],   # list[str] of user-defined card type names
    # Overrides for the built-in types (models.CARD_TYPES): renaming a
    # built-in stores {original_name: current_name} here rather than
    # mutating the CARD_TYPES constant itself, so color/icon lookups
    # (keyed off the *original* name in CARD_COLORS/CARD_TYPE_ICONS)
    # keep working after a rename. deleted_builtin_types lists original
    # names hidden from the type pickers; their cards are reassigned like
    # any deleted custom type. See Storage.rename_card_type/
    # delete_card_type below.
    "builtin_type_renames": {},
    "deleted_builtin_types": [],
    # Accessibility
    "large_text": False,
    "reduced_motion": False,
    "focus_outlines": True,
    # project_id -> last external file path used by that project's Save
    # As / Quick Save (see main_window._last_saved_paths). Persisted
    # (unlike the in-memory dict it seeds) so a project that was already
    # saved to a file in a previous run doesn't prompt with a Save As
    # dialog again on its first Quick Save this session.
    "last_saved_paths": {},
    # General
    "remember_last_project": True,
    "double_click_opens_card": True,
    "uppercase_card_text": True,   # display-only; see card_widget.FeatureCardWidget.uppercase_card_text
    # Accessibility
    "larger_click_targets": False,
    "always_show_drop_zones": False,
    # UI scale: percentage applied on top of the base font/control sizes
    # (100 = normal). Extends the existing "Larger text" toggle rather
    # than replacing it -- see styles.build_stylesheet and
    # MainWindow._apply_theme/_topbar_capture_base_sizes, which already
    # special-case a fixed +2px "large_text" bump; ui_scale generalizes
    # that same mechanism to an adjustable, continuous factor. 100 is a
    # careful no-op: every existing install with no ui_scale key yet
    # renders pixel-for-pixel identical to before this setting existed.
    "ui_scale": 100,
    "ui_font": "SF Pro Text",
    "reader_font_size": 12,
}


def _project_hash(project: Project) -> str:
    """Cheap content fingerprint of a project's persisted shape, used to
    detect whether a project actually changed since it was last written
    to disk. Sorting keys makes the hash independent of dict insertion
    order (to_dict()'s own key order never changes today, but this keeps
    the fingerprint stable even if that ever shifted), and json.dumps is
    already exactly the serialization save() is about to write anyway, so
    this doubles as a cheap correctness check with no separate comparison
    logic to maintain."""
    payload = json.dumps(project.to_dict(), sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _safe_project_filename(project_id: str) -> str:
    """📁 Safe IDs stay readable; unusual IDs get distinct file names."""
    safe = "".join(c for c in project_id if c.isascii() and (c.isalnum() or c in "-_"))
    if safe == project_id and safe and len(safe) <= 100:
        return f"{safe}.json"
    return "project-" + hashlib.sha256(project_id.encode("utf-8")).hexdigest() + ".json"


class Storage:
    def __init__(self, data_dir=None):
        self.data_dir = os.fspath(data_dir) if data_dir is not None else get_data_dir()
        self.last_save_ok = True
        self.save_status_handler = None
        self.recovery_messages = []
        self.projects_dir = os.path.join(self.data_dir, "projects")
        self.index_path = os.path.join(self.data_dir, "index.json")
        # Legacy single-file path, kept only so the migration step can
        # find and import it on first run against an old install.
        self.legacy_file_path = os.path.join(self.data_dir, "whiteboard_data.json")
        os.makedirs(self.projects_dir, exist_ok=True)
        self.attachments = AttachmentStore(self.data_dir)

        self.projects: List[Project] = []
        self.active_project_id: Optional[str] = None
        self.settings: dict = copy.deepcopy(DEFAULT_SETTINGS)

        # project_id -> hash of the content last written to (or read from)
        # disk for that project, and project_id -> its on-disk file path.
        # Used by save() to skip rewriting any project whose content
        # hasn't actually changed, so e.g. renaming one project or editing
        # one card only ever touches that project's own file.
        self._on_disk_hash: Dict[str, str] = {}
        self._project_paths: Dict[str, str] = {}

        self._migrate_legacy_file_if_needed()
        self.load()

    # ------------------------------------------------------------ loading
    def _migrate_legacy_file_if_needed(self):
        """One-time import of the old monolithic whiteboard_data.json into
        the new per-project layout. Runs before load() and only if the new
        index doesn't exist yet but the old file does, so it never
        overwrites a project layout that's already been migrated (or a
        fresh install that never had the old file). The old file is
        renamed aside (not deleted) once every project inside it has been
        written out successfully, so a failure partway through leaves the
        original file intact for the next launch to retry against."""
        if os.path.exists(self.index_path):
            return
        if not os.path.exists(self.legacy_file_path):
            return
        try:
            with open(self.legacy_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError, UnicodeError):
            # Unreadable legacy file: nothing to migrate. Leave it in
            # place untouched -- load() below will simply start fresh,
            # same as any other corrupt-file case, and the untouched
            # legacy file is preserved for manual recovery if needed.
            return

        try:
            legacy_projects = [Project.from_dict(p) for p in data.get("projects", [])]
            legacy_settings = data.get("settings", {})
            if not isinstance(legacy_settings, dict):
                legacy_settings = {}
        except (TypeError, AttributeError, ValueError):
            self.recovery_messages.append("The old data file could not be read. Its original copy was kept.")
            return
        legacy_active_id = data.get("active_project_id")

        # Stage into self.projects temporarily so _write_index (which
        # reads self.projects to build project_ids) sees the right list.
        self.projects = legacy_projects
        try:
            for project in legacy_projects:
                self._write_project_file(project)
            self._write_index(legacy_active_id, {**DEFAULT_SETTINGS, **legacy_settings})
        except OSError:
            # Partial migration: don't leave a half-written index/project
            # set around to be picked up as "the real data" next launch.
            # Clean up anything this attempt created and let the legacy
            # file be retried on the next launch instead.
            for project in legacy_projects:
                try:
                    os.remove(self._project_path(project.id))
                except OSError:
                    pass
            try:
                os.remove(self.index_path)
            except OSError:
                pass
            self.projects = []
            return
        finally:
            self.projects = []

        try:
            os.replace(self.legacy_file_path, self.legacy_file_path + ".migrated")
        except OSError:
            pass  # cosmetic cleanup only; migration itself already succeeded

    def _project_path(self, project_id: str) -> str:
        return os.path.join(self.projects_dir, _safe_project_filename(project_id))

    def load(self):
        self.projects = []
        self.active_project_id = None
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self._on_disk_hash = {}
        self._project_paths = {}

        index = self._read_index()
        known_ids = index.get("project_ids")
        if not isinstance(known_ids, list):
            known_ids = None
        if known_ids is None:
            # No index yet (fresh install, or an index that predates the
            # project_ids list): fall back to scanning the projects
            # directory for whatever .json files are actually there,
            # so a hand-copied or partially-restored projects folder
            # still loads instead of appearing empty.
            known_ids = self._discover_project_ids_from_disk()

        loaded_ids = set()
        for project_id in known_ids:
            if not isinstance(project_id, str) or not project_id or project_id in loaded_ids:
                continue
            loaded_ids.add(project_id)
            project = self._read_project_file(project_id)
            if project is not None and not any(p.id == project.id for p in self.projects):
                self.projects.append(project)

        active_id = index.get("active_project_id")
        if active_id is not None and not any(p.id == active_id for p in self.projects):
            # Stale/orphaned active id (e.g. that project's file was
            # deleted or failed to load): fall back to the first project
            # so the selector and the rendered board stay in sync.
            active_id = self.projects[0].id if self.projects else None
        self.active_project_id = active_id

        loaded_settings = index.get("settings", {})
        if not isinstance(loaded_settings, dict):
            loaded_settings = {}
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.settings.update(loaded_settings)
        for key, default in DEFAULT_SETTINGS.items():
            value = self.settings.get(key)
            if not isinstance(value, type(default)):
                self.settings[key] = copy.deepcopy(default)
        for key in ("custom_card_types", "deleted_builtin_types"):
            self.settings[key] = [v for v in self.settings[key] if isinstance(v, str)]
        for key in ("builtin_type_renames", "last_saved_paths"):
            self.settings[key] = {k: v for k, v in self.settings[key].items() if isinstance(v, str)}
        self.settings["ui_scale"] = max(80, min(150, self.settings["ui_scale"]))
        self.settings["reader_font_size"] = max(8, min(32, self.settings["reader_font_size"]))

    def _discover_project_ids_from_disk(self) -> List[str]:
        try:
            names = os.listdir(self.projects_dir)
        except OSError:
            return []
        ids = []
        for name in sorted(names):
            if name.endswith(".json") and not name.endswith(".tmp"):
                ids.append(name[: -len(".json")])
        return ids

    def _read_index(self) -> dict:
        if not os.path.exists(self.index_path):
            return {}
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("The saved index must be a JSON object.")
            return data
        except (ValueError, OSError, UnicodeError):
            # Corrupt/unreadable index: back it up and start fresh. Any
            # project files on disk are untouched and get picked up via
            # the directory-scan fallback in load() above, so a broken
            # index alone doesn't lose project data, only the remembered
            # active-project selection and settings.
            try:
                self._quarantine(self.index_path)
            except OSError:
                pass
            return {}

    def _read_project_file(self, project_id: str) -> Optional[Project]:
        path = self._project_path(project_id)
        if not os.path.exists(path):
            legacy_name = "".join(c for c in project_id if c.isalnum() or c in "-_") or "project"
            legacy_path = os.path.join(self.projects_dir, legacy_name + ".json")
            if os.path.exists(legacy_path):
                path = legacy_path
        self._project_paths[project_id] = path
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            project = Project.from_dict(data)
            embedded = isinstance(data, dict) and (data.get('attachment_files') or any('data' in a for c in project.cards for a in c.attachments))
            if embedded:
                self.attachments.import_project(project, data.get('attachment_files'))
        except (json.JSONDecodeError, OSError, TypeError, AttributeError, ValueError, UnicodeError):
            # Corrupt/unreadable project file: back it up and skip it,
            # rather than letting one bad project file take down the
            # whole app (or silently vanish with no trace) -- every
            # *other* project still loads normally, which is the whole
            # point of the per-project split.
            try:
                self._quarantine(path)
            except OSError:
                pass
            return None
        # Seed the on-disk hash from what was just read, so save() doesn't
        # rewrite this project's file on the very next save unless it's
        # actually been modified since load.
        self._project_paths[project.id] = path
        if project_id != project.id:
            self._project_paths.pop(project_id, None)
        if path == self._project_path(project.id) and not embedded:
            self._on_disk_hash[project.id] = _project_hash(project)
        return project

    def _quarantine(self, path):
        backup = path + ".bak"
        count = 1
        while os.path.exists(backup):
            backup = path + f".bak.{count}"
            count += 1
        os.replace(path, backup)
        self.recovery_messages.append(f"An unreadable file was kept at {backup}.")

    # ------------------------------------------------------------- saving
    def _write_project_file(self, project: Project) -> bool:
        path = self._project_path(project.id)
        atomic_write_json(path, project.to_dict())
        self._project_paths[project.id] = path
        return True

    def _write_index(self, active_project_id: Optional[str], settings: dict):
        data = {
            "active_project_id": active_project_id,
            # Ordered list of known project ids, so load() can restore
            # projects in a stable order even though a directory listing
            # isn't guaranteed to be (and so a project whose file is
            # temporarily missing/corrupt is still remembered as
            # "supposed to exist" rather than quietly forgotten).
            "project_ids": [p.id for p in self.projects],
            "settings": settings,
        }
        atomic_write_json(self.index_path, data)

    def save(self) -> bool:
        """Persist all pending changes to disk. Returns True on success,
        False if any write failed (disk full, permission denied, AppData
        briefly unreachable, etc). Every caller in this app is a UI action
        (add/edit/delete card, rename project, change a setting, ...)
        invoked directly from a Qt slot, so letting an OSError escape here
        would propagate out of that slot uncaught -- PySide6 doesn't
        recover from that gracefully, so it can crash the whole app
        instead of just failing the one save. Callers that want to tell
        the user should check the return value; callers that don't care
        can ignore it, same as before, but the app itself never goes down
        over a failed write.

        Unlike the old single-file design, this only rewrites: (a) each
        project whose serialized content has actually changed since it
        was last read from or written to disk (tracked via a content hash
        in _on_disk_hash, so an unrelated project's card edit never
        rewrites this project's file), and (b) the small index file,
        which is cheap regardless since it holds no card/column data. A
        project deleted since the last save has its on-disk file removed
        the same way. This keeps per-action save cost proportional to the
        one project actually being edited, not to the total data across
        every project -- the whole point of the per-project split."""
        ok = True

        current_ids = {p.id for p in self.projects}
        stale_ids = set(self._project_paths) - current_ids

        for project in self.projects:
            new_hash = _project_hash(project)
            if self._on_disk_hash.get(project.id) == new_hash:
                continue  # unchanged since last write -- nothing to do
            try:
                self._write_project_file(project)
                self._on_disk_hash[project.id] = new_hash
            except OSError:
                ok = False

        if ok:
            try:
                self._write_index(self.active_project_id, self.settings)
            except OSError:
                ok = False

        if ok:
            for stale_id in stale_ids:
                path = self._project_paths.pop(stale_id, None)
                self._on_disk_hash.pop(stale_id, None)
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
        self.last_save_ok = ok
        if self.save_status_handler:
            self.save_status_handler(ok)
        return ok

    def save_project(self, project_id: str) -> bool:
        """Persist just one project (plus the index, which is cheap
        regardless) rather than checking every loaded project's hash --
        a small optimization for call sites that already know exactly
        which project changed. Falls back to a normal save() if the
        project isn't found (e.g. already deleted), so this is always
        safe to call. Behaves the same as save() on failure/success."""
        project = self.get_project(project_id)
        if project is None:
            return self.save()
        ok = True
        new_hash = _project_hash(project)
        if self._on_disk_hash.get(project.id) != new_hash:
            try:
                self._write_project_file(project)
                self._on_disk_hash[project.id] = new_hash
            except OSError:
                ok = False
        if ok:
            try:
                self._write_index(self.active_project_id, self.settings)
            except OSError:
                ok = False
        self.last_save_ok = ok
        if self.save_status_handler:
            self.save_status_handler(ok)
        return ok

    def file_size_bytes(self) -> int:
        """Total on-disk size (index + every project file) in bytes, or 0
        if nothing has been saved yet. Used by the Settings > Diagnostics
        tab. Best-effort (never raises) -- a missing/unreadable file just
        doesn't contribute to the total rather than crashing Settings."""
        total = 0
        for path in [self.index_path] + list(self._project_paths.values()):
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        return total

    # --- Settings helpers --------------------------------------------------

    def get_setting(self, key, default=None):
        return self.settings.get(key, DEFAULT_SETTINGS.get(key, default))

    def set_setting(self, key, value):
        self.settings[key] = value
        return self.save()

    def update_settings(self, values: dict):
        """Apply multiple settings in one shot and persist with a single
        save(), instead of calling set_setting() per key (each of which
        would otherwise trigger its own index write). Skips the write
        entirely if every incoming value already matches what's stored
        (e.g. the user opened Settings and pressed OK without changing
        anything)."""
        if all(self.settings.get(k) == v for k, v in values.items()):
            return self.last_save_ok
        self.settings.update(values)
        return self.save()

    def add_custom_card_type(self, type_name: str, defer_save: bool = False):
        """Register a new custom card type. Callers that will immediately
        perform another save() of their own (e.g. after also appending the
        new card) can pass defer_save=True to avoid writing to disk twice
        for a single logical action."""
        types = self.settings.setdefault("custom_card_types", [])
        if type_name and type_name not in types:
            types.append(type_name)
            if not defer_save:
                return self.save()

    def rename_custom_card_type(self, old_name: str, new_name: str) -> bool:
        """Rename a custom card type in place (keeping its position in the
        list, so its color/icon -- both derived from list index, see
        models.card_type_color/card_type_icon -- stay the same) and update
        every card across every loaded project that currently uses it, so
        no card is silently left referencing a type name that no longer
        exists in the list. Returns False (no-op) if old_name isn't a
        registered custom type, new_name is empty, or new_name collides
        with another existing type (built-in or custom); True otherwise.
        Kept as a thin wrapper around rename_card_type for the custom-only
        case -- see that method for the built-in-type path."""
        types = self.settings.get("custom_card_types", [])
        if old_name not in types:
            return False
        return self.rename_card_type(old_name, new_name)

    def delete_custom_card_type(self, type_name: str, reassign_to: str = None):
        """Remove a custom card type and reassign every card that used it.
        Kept as a thin wrapper around delete_card_type for the
        custom-only case -- see that method for the built-in-type path."""
        types = self.settings.get("custom_card_types", [])
        if type_name not in types:
            return
        self.delete_card_type(type_name, reassign_to)

    def rename_card_type(self, old_name: str, new_name: str) -> bool:
        """Rename any card type -- built-in or custom -- in place, and
        update every card across every loaded project that currently uses
        it. Returns False (no-op) if old_name isn't a currently-available
        type, new_name is empty, or new_name collides with another
        existing type; True otherwise.

        For a custom type this rewrites its entry in custom_card_types,
        exactly as rename_custom_card_type always did. For a built-in
        type this instead records {original_name: new_name} in
        builtin_type_renames -- the CARD_TYPES/CARD_COLORS/
        CARD_TYPE_ICONS constants stay keyed by the type's *original*
        name so its color/icon assignment is preserved across the
        rename, and models.card_type_color/card_type_icon resolve the
        rename via this same mapping (passed as builtin_renames)."""
        custom_types = self.settings.setdefault("custom_card_types", [])
        builtin_renames = self.settings.setdefault("builtin_type_renames", {})
        deleted_builtins = self.settings.get("deleted_builtin_types", [])

        available = self.available_card_types()
        if old_name not in available or not new_name or new_name == old_name:
            return False
        if new_name in available:
            return False

        if old_name in custom_types:
            custom_types[custom_types.index(old_name)] = new_name
        else:
            # old_name is a built-in's *current* (possibly already
            # renamed) display name -- find its original CARD_TYPES key
            # so the override maps from the stable original, not from
            # whatever the previous display name happened to be.
            original = old_name
            for orig, current in builtin_renames.items():
                if current == old_name:
                    original = orig
                    break
            if original in deleted_builtins:
                return False
            builtin_renames[original] = new_name

        for project in self.projects:
            for card in project.cards:
                if card.card_type == old_name:
                    card.card_type = new_name
        return self.save()

    def delete_card_type(self, type_name: str, reassign_to: str = None):
        """Remove any card type -- built-in or custom -- from the type
        pickers and reassign every card that used it to reassign_to
        (falling back to the first remaining available type if none is
        given), across every loaded project. No-op if type_name isn't
        currently available, or if it's the last remaining type (at
        least one type must always exist for cards to fall back to).

        A deleted built-in is recorded in deleted_builtin_types (by its
        original CARD_TYPES name) rather than removed from CARD_TYPES
        itself, so the constant stays a stable, complete reference of
        every color/icon this app ships with."""
        custom_types = self.settings.setdefault("custom_card_types", [])
        builtin_renames = self.settings.setdefault("builtin_type_renames", {})
        deleted_builtins = self.settings.setdefault("deleted_builtin_types", [])

        available = self.available_card_types()
        if type_name not in available or len(available) <= 1:
            return

        fallback = reassign_to
        if not fallback:
            remaining = [t for t in available if t != type_name]
            fallback = remaining[0] if remaining else ""

        if type_name in custom_types:
            custom_types.remove(type_name)
        else:
            original = type_name
            for orig, current in builtin_renames.items():
                if current == type_name:
                    original = orig
                    break
            if original not in deleted_builtins:
                deleted_builtins.append(original)

        for project in self.projects:
            for card in project.cards:
                if card.card_type == type_name:
                    card.card_type = fallback
        return self.save()

    def available_card_types(self) -> List[str]:
        """Every card type currently offered by the type pickers, in
        display order: built-ins first (in their declared CARD_TYPES
        order, renamed where overridden and skipping any deleted),
        then custom types in the order they were created. The single
        source of truth for "what types exist right now" -- used by
        rename_card_type/delete_card_type above to validate names and
        by MainWindow._available_card_types() to populate every type
        picker in the UI."""
        builtin_renames = self.settings.get("builtin_type_renames", {})
        deleted_builtins = set(self.settings.get("deleted_builtin_types", []))
        result = [
            builtin_renames.get(t, t)
            for t in CARD_TYPES
            if t not in deleted_builtins
        ]
        result.extend(self.settings.get("custom_card_types", []))
        return result

    def palette_card_types(self) -> List[str]:
        """Card types that need a palette-cycled color/icon rather than
        one of the fixed CARD_COLORS/CARD_TYPE_ICONS entries: every
        custom type, plus any built-in's *current* name after a rename
        (a rename moves its display name out from under the original
        CARD_COLORS/CARD_TYPE_ICONS key, exactly like a brand-new custom
        type -- see models.card_type_color/card_type_icon). Order
        matches available_card_types() minus the never-renamed built-ins,
        so a given renamed/custom type keeps a stable palette index."""
        builtin_renames = self.settings.get("builtin_type_renames", {})
        deleted_builtins = set(self.settings.get("deleted_builtin_types", []))
        result = [
            builtin_renames[t]
            for t in CARD_TYPES
            if t not in deleted_builtins and t in builtin_renames
        ]
        result.extend(self.settings.get("custom_card_types", []))
        return result

    # --- Project helpers -------------------------------------------------

    def get_project(self, project_id: str) -> Optional[Project]:
        for p in self.projects:
            if p.id == project_id:
                return p
        return None

    def add_project(self, project: Project):
        self.projects.append(project)
        self.active_project_id = project.id
        return self.save()

    def delete_project(self, project_id: str):
        # Skip the write entirely if project_id doesn't match anything --
        # avoids an unnecessary index rewrite for a no-op call.
        if not any(p.id == project_id for p in self.projects):
            return
        self.projects = [p for p in self.projects if p.id != project_id]
        if self.active_project_id == project_id:
            self.active_project_id = self.projects[0].id if self.projects else None
        return self.save()

    def rename_project(self, project_id: str, new_name: str):
        p = self.get_project(project_id)
        if p and p.name != new_name:
            p.name = new_name
            self.save_project(project_id)
