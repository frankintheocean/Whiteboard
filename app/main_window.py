"""🪟 Show projects and board actions."""
from smooth_scroll import SmoothScrollArea
import copy
import json
import os
import time

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox, QApplication, QToolButton, QFileDialog,
    QLayout, QFrame, QSizePolicy, QMenu
)
from PySide6.QtCore import Qt, QTimer, QRect, QSize, QPoint
from PySide6.QtGui import QFont, QFontMetrics, QTextDocument, QKeySequence, QShortcut

from models import (
    Project, Card, Column, new_id, PRIORITY_LEVELS, priority_label,
)
from storage import Storage
from column_widget import ColumnWidget, COLUMN_WIDTH, COLUMN_MAX_WIDTH, COLUMN_MIN_WIDTH, SORT_BOARD_ORDER
from dialogs import (
    CardDialog, TextPromptDialog, NewProjectDialog, SettingsDialog, FitPopupComboBox,
    ManageCardTypesDialog,
)
from toast import ToastHost
import styles
import app_meta
import error_log
from file_io import atomic_write_json
from workspace_panel import WorkspacePanel
from quick_find import QuickFindDialog, FindEntry
from card_tools import search_text, apply_card_details, due_text
from reminders import ReminderService
from attachments import MAX_PROJECT_BYTES, project_file_bytes
from view_state import remap_view_columns

# Layout metrics used for the "window follows content" sizing behavior.
BOARD_MARGIN = 16       # matches board_layout contents margins (left+right identical)
BOARD_SPACING = 16      # matches board_layout spacing between columns
TOPBAR_HEIGHT = 56
MIN_WINDOW_HEIGHT = 500
MAX_WINDOW_WIDTH_FRACTION = 0.92   # never grow wider than this fraction of the screen


class FlowLayout(QLayout):
    """A simple left-to-right, top-to-bottom wrapping layout (Qt has no
    built-in equivalent). Used for the multi-select bulk-action bar (see
    _build_ui) so its buttons wrap onto a second row on a narrow window
    instead of being clipped or forcing the window wider -- unlike a
    plain QHBoxLayout, which never wraps and unlike the top bar's own
    scroll-area-plus-font-scaling approach (see _apply_topbar_scale),
    which wouldn't suit a handful of full-size action buttons that need
    to stay tappable/legible at any width."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 8):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only: bool):
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x = effective.x()
        y = effective.y()
        line_height = 0
        spacing = self._spacing

        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisible():
                continue
            item_size = item.sizeHint()
            next_x = x + item_size.width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + spacing
                next_x = x + item_size.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))
            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + bottom


class MainWindow(QMainWindow):
    def __init__(self, storage: Storage):
        super().__init__()
        self.storage = storage
        self.setWindowTitle(f"\U0001F4CB WhiteBoard {app_meta.APP_VERSION}")
        self._apply_theme(self.storage.get_setting("theme", styles.DEFAULT_THEME))

        self._column_widgets = {}  # column_id -> ColumnWidget

        # Each column's chosen "Sort by" mode/direction (see
        # ColumnWidget.sortStateChanged), keyed by project_id then
        # column_id: {project_id: {column_id: (sort_key, descending)}}.
        # ColumnWidget itself is torn down and rebuilt on every project
        # switch/column change, so this dict is what actually survives
        # that rebuild -- restored via initial_sort_key/
        # initial_sort_descending when each ColumnWidget is constructed in
        # _load_active_project, and updated live as the user changes a
        # column's sort. Session/UI-only, same as the type filter: never
        # written to disk, never affects card.order.
        self._column_sort_state = {}  # project_id -> {column_id: (key, desc)}

        # One-shot undo buffer for Settings > Diagnostics > Clear Board:
        # holds (project_id, columns, cards) from immediately before the
        # last clear, so Undo can restore exactly what was removed. Reset
        # (cleared) whenever Settings is opened, so a stale undo can never
        # apply to state that's since moved on to a different project or
        # session.
        self._board_clear_undo = None

        # Tracks whether the person has manually resized the window
        # horizontally, so later column add/remove/reload actions don't
        # silently snap a deliberately-resized window back to its
        # content-fit width (see resizeEvent / _update_window_width).
        self._user_resized_width = False
        self._resizing_programmatically = False
        # One-shot guard for the post-show initial sizing (see showEvent).
        self._did_initial_show_resize = False
        # One-shot guard for the post-show dark title bar (see showEvent).
        self._did_dark_title_bar = False

        # Debounce timer for redistributing extra window width across
        # columns during a live resize drag (see resizeEvent and
        # _apply_column_stretch_width).
        # Per-project Quick Save target: project_id -> last file path used
        # by Save As or Quick Save. Seeded from storage settings so a
        # project already saved to a file in a previous run keeps that
        # target across restarts too (otherwise Quick Save's first call
        # this session would always fall back to a Save As prompt, even
        # for a project that's genuinely already been saved before).
        # Pruned to only known projects, since a saved path for a project
        # that's since been deleted has nothing left to quick-save to.
        known_ids = {p.id for p in storage.projects}
        self._last_saved_paths = {
            pid: path
            for pid, path in storage.get_setting("last_saved_paths", {}).items()
            if pid in known_ids and isinstance(path, str) and path
        }
        # Per-project dirty flag relative to that project's own
        # _last_saved_paths entry: True once the project has changed
        # since the last time it was written to an *external* Save As /
        # Quick Save file (independent of the app's own AppData
        # autosave, which always persists immediately regardless). Only
        # tracked for projects that have ever been saved to an external
        # file this session -- a project with no _last_saved_paths entry
        # has nothing to "lose" on close beyond what's already safely on
        # disk in AppData, so it's never flagged dirty here.
        self._external_dirty = set()

        # Non-blocking toast host for save/undo/redo/error notifications,
        # instead of modal QMessageBox popups for low-stakes confirmations
        # (see toast.py). Theme is kept in sync from _apply_theme below.
        self._toast_host = ToastHost(self)

        # Undo/redo stack for card and column edits/moves/deletes (Ctrl+Z /
        # Ctrl+Y), separate from the one-shot Diagnostics > Clear Board
        # undo above (_board_clear_undo), which only ever covers that one
        # specific action. Each entry is (undo_fn, redo_fn, project_id) --
        # both closures capture whatever state they need to fully restore
        # the project to its pre/post-action shape. Bounded so a very long
        # session doesn't grow this without limit.
        self._undo_stack = []
        self._redo_stack = []
        self._UNDO_LIMIT = 100
        # Guard so undo/redo's own project mutations don't re-push
        # themselves back onto the stack as if they were new user actions.
        self._applying_undo_redo = False

        # Multi-select: card ids currently selected via Shift/Ctrl-click,
        # for bulk move/delete/type-change. Session/UI-only, like the
        # per-column type filter -- cleared on project switch/reload,
        # never persisted. selection_anchor is the last plain (non-
        # modified) click, used as the start point for a Shift range-select.
        self._selected_card_ids = set()
        self._selection_anchor = None

        self._column_stretch_timer = QTimer(self)
        self._column_stretch_timer.setSingleShot(True)
        self._column_stretch_timer.timeout.connect(self._apply_column_stretch_width)

        # Debounce timer for rescaling the top bar's own buttons/labels as
        # the window is resized (see resizeEvent and _apply_topbar_scale).
        # Kept separate from the column-stretch timer above so a resize
        # doesn't have to wait on column relayout (or vice versa) before
        # the toolbar itself responds.
        self._topbar_scale_timer = QTimer(self)
        self._topbar_scale_timer.setSingleShot(True)
        self._topbar_scale_timer.timeout.connect(self._apply_topbar_scale)
        # Cache of each top-bar widget's natural (100%-scale) font pixel
        # size, captured once in _build_ui so repeated rescales always
        # scale from the same baseline instead of compounding shrink/grow
        # calls against an already-scaled size.
        self._topbar_base_point_sizes = {}
        self._topbar_scale_factor = 1.0

        # No explicit min/max size is ever set on this window, but on
        # Windows, resizing a QMainWindow with resize() *before* it has
        # ever been shown -- and doing so twice back-to-back with no event
        # loop turn in between, as this used to do (once inside
        # _load_active_project() via _update_window_width(), then again
        # right after) -- can make the platform plugin snapshot a stale
        # layout-derived size as the window's effective min/max, so the OS
        # then refuses horizontal/diagonal edge-drag resizing until
        # something else (e.g. maximizing) forces Qt to recompute it.
        # Explicitly clearing both to "unbounded" up front, and doing the
        # real content-fit sizing once after the window is actually shown
        # (see showEvent), avoids ever handing the OS a stale constraint.
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)  # Qt's own QWIDGETSIZE_MAX

        # Clearing min/max after the fact (showEvent/resizeEvent below)
        # only fixes the symptom *once Qt has already recomputed it* --
        # QLayout::activate() re-derives a fresh min/max straight from the
        # layout tree on essentially every relayout (including ones that
        # happen mid native-resize on Windows, where the OS's live resize
        # loop doesn't reliably interleave with our resizeEvent handler on
        # every frame). That's why the previous fix only actually took
        # effect after a column add/remove forced a full rebuild through
        # _load_active_project() -- that path happened to run late enough,
        # after the belt-and-braces clears, to "win" the race. A window
        # whose central layout was never asked to derive a size constraint
        # in the first place can't reintroduce a stale one, regardless of
        # timing, so this is set once here rather than being fought after
        # every relayout.

        self._build_ui()
        # Belt-and-braces companion to the min/max clearing above: tell the
        # central widget's own layout to never derive a min/max size
        # constraint for this window from its content at all (rather than
        # deriving one and then having us clear it afterward, which is
        # inherently a step behind whatever Qt/the OS just did). This is
        # what actually makes free horizontal/diagonal edge-drag resizing
        # work universally and immediately, not only after something else
        # (like a column delete+re-add forcing a full rebuild) happens to
        # re-run the clearing code late enough to win the race.
        central_layout = self.centralWidget().layout()
        if central_layout is not None:
            central_layout.setSizeConstraint(QLayout.SetNoConstraint)
        self._ensure_project_exists()
        # "Reopen last active project" (General settings) defaults to on,
        # matching prior behavior (storage.load() already restores
        # active_project_id from the index). When turned off, start on
        # the alphabetically-first project instead -- same starting point
        # _refresh_project_selector falls back to below when there's no
        # match, so this only overrides which project counts as active,
        # not how the selector itself resolves ties.
        if not self.storage.get_setting("remember_last_project", True) and self.storage.projects:
            first = min(self.storage.projects, key=lambda p: p.name.casefold())
            self.storage.active_project_id = first.id
        from card_widget import FeatureCardWidget
        FeatureCardWidget.double_click_opens_card = self.storage.get_setting("double_click_opens_card", True)
        FeatureCardWidget.uppercase_card_text = self.storage.get_setting("uppercase_card_text", True)
        self._refresh_project_selector()
        self._load_active_project()

        # Ctrl+S: Word-style quicksave -- re-saves straight back to the
        # project's already-known file with no dialog, falling back to a
        # Save As-style prompt only the first time (same behavior as the
        # Quick Save button; see _on_quick_save_file). Window-scoped
        # (not per-widget) so it fires regardless of which widget has
        # focus, matching how Ctrl+S behaves in Word/most editors.
        quick_save_shortcut = QShortcut(QKeySequence.Save, self)
        quick_save_shortcut.setContext(Qt.WindowShortcut)
        quick_save_shortcut.activated.connect(self._on_quick_save_file)
        for key, callback in (("Ctrl+N", self._on_new_card_default),
                              ("Ctrl+O", self._on_open_file),
                              ("Ctrl+Shift+S", self._on_save_file)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(callback)


        # General Ctrl+Z / Ctrl+Y (and Ctrl+Shift+Z, the common redo
        # alternate) for card/column create/edit/delete/move actions --
        # see _push_undo/_undo/_redo below. Window-scoped like Ctrl+S
        # above so it works regardless of which widget has focus, except
        # while a text-editing widget (a dialog's line edit, the rich
        # description editor, the inline quick-add field) has focus --
        # those already have their own native Ctrl+Z/Ctrl+Y text-undo via
        # Qt, which must keep working for in-progress typing rather than
        # being shadowed by the board-level undo stack.
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.setContext(Qt.WindowShortcut)
        undo_shortcut.activated.connect(self._on_undo_shortcut)

        redo_shortcut = QShortcut(QKeySequence.Redo, self)
        redo_shortcut.setContext(Qt.WindowShortcut)
        redo_shortcut.activated.connect(self._on_redo_shortcut)
        redo_alt_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        redo_alt_shortcut.setContext(Qt.WindowShortcut)
        redo_alt_shortcut.activated.connect(self._on_redo_shortcut)

        # Delete/Backspace: bulk-delete the current multi-selection, when
        # there is one and no text-editing widget has focus (see the same
        # focused-widget guard used for undo/redo above).
        delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self)
        delete_shortcut.setContext(Qt.WindowShortcut)
        delete_shortcut.activated.connect(self._on_delete_shortcut)

        # Escape clears the current multi-selection, matching common
        # list/file-manager convention. Harmless no-op when nothing is
        # selected (see _clear_selection's own early-return).
        escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        escape_shortcut.setContext(Qt.WindowShortcut)
        escape_shortcut.activated.connect(self._clear_selection)
        for key, callback in (("Ctrl+F", self._open_search), ("Ctrl+K", self._open_palette)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
        self.reminders = ReminderService(self)


    def _open_search(self):
        self._find(False)

    def _open_palette(self):
        self._find(True)

    def _find(self, palette):
        entries = []
        if palette:
            actions = [("New card", "Add a card to this project", self._on_new_card_default),
                       ("New project", "Create a project", self._on_new_project),
                       ("Settings", "Change fonts and themes", self._on_open_settings),
                       ("Open project file", "Open a saved project", self._on_open_file),
                       ("Import project", "Import a separate copy", self._on_import_file),
                       ("Save As", "Export a project with its files", self._on_save_file),
                       ("Quick Save", "Update the saved project file", self._on_quick_save_file),
                       ("Undo", "Undo a board change", self._on_undo_shortcut),
                       ("Redo", "Redo a board change", self._on_redo_shortcut),
                       ("Switch board or list", "Change the project view", self._toggle_view),
                       ("Save current view", "Remember these filters and widths", self.workspace.save_view),
                       ("Clear filters", "Show all cards in this project", self.workspace.clear_filters),
                       ("Auto column widths", "Reset manual widths", self.workspace.reset_widths)]
            for title, detail, callback in actions:
                entries.append(FindEntry(title, detail, (title + ' ' + detail).casefold(), callback, 'command'))
        for project in sorted(self.storage.projects, key=lambda p: p.name.casefold()):
            if palette:
                entries.append(FindEntry(project.name, 'Open project', project.name.casefold(), lambda pid=project.id: self._activate_project(pid), 'project'))
            columns = {c.id: c.name for c in project.columns}
            for card in project.cards:
                entries.append(FindEntry(card.title, project.name + ' · ' + columns.get(card.column_id, ''), search_text(project, card),
                    lambda pid=project.id, cid=card.id: self._open_found_card(pid, cid)))
        dialog = QuickFindDialog(entries, self, palette)
        if dialog.exec() and dialog.selected_entry:
            dialog.selected_entry.callback()

    def _activate_project(self, project_id):
        if self.storage.get_project(project_id) is not None:
            self.storage.active_project_id = project_id
            self._refresh_project_selector()
            self._load_active_project()
            self._save()

    def _open_found_card(self, project_id, card_id):
        self._activate_project(project_id)
        self._on_edit_card(card_id)

    def _toggle_view(self):
        self.workspace.mode.setCurrentIndex(1 - self.workspace.mode.currentIndex())

    def _attachment_budget(self, exclude_card=None):
        project = self.active_project
        used = project_file_bytes(project, exclude_card) if project else 0
        return max(0, MAX_PROJECT_BYTES - used)

    def _on_column_width_changed(self, column_id, width):
        if self.active_project:
            for column in self.active_project.columns:
                if column.id == column_id:
                    column.width = width
            self._apply_column_stretch_width()
            self._save(self.active_project.id)

    def showEvent(self, event):
        super().showEvent(event)
        # Dark title bar (Windows 10 1809+/11), same mechanism and same
        # best-effort/no-crash guarantee as the build progress popup (see
        # build/build_progress.py) -- asks the OS compositor directly via
        # DWM's "immersive dark mode" window attribute rather than
        # anything Qt itself has a theming API for. Applied once per show,
        # here rather than deferred via singleShot(0, ...) like
        # _apply_initial_size below: unlike that Tk popup (which needed an
        # explicit update_idletasks() first to get a real HWND), Qt has
        # already created this window's native handle by the time
        # showEvent is delivered, so there's no settling to wait on.
        if not self._did_dark_title_bar:
            self._did_dark_title_bar = True
            self._apply_dark_title_bar()
        # Content-fit initial size is applied here (post-show, post-layout-
        # activation) instead of in __init__, and only once -- see below.
        # Deferred one event-loop turn via QTimer.singleShot(0, ...)
        # rather than resized synchronously inside showEvent itself:
        # resizing while this event is still being processed can be
        # layout-ineffective on Windows (the frame/decoration geometry
        # isn't fully settled yet), which left visible dead space on the
        # right of the window on first open even though the same width
        # math was correct. Letting the event loop turn once first means
        # this runs against the window's actual, final on-screen geometry.
        if not self._did_initial_show_resize:
            self._did_initial_show_resize = True
            QTimer.singleShot(0, self._apply_initial_size)

    def _apply_dark_title_bar(self):
        """Best-effort only, exactly like the build popup's own version of
        this: any failure (older Windows, non-Windows OS, ctypes
        unavailable) just leaves the default title bar rather than raising,
        since this is purely cosmetic on top of the app's own already-dark
        default theme."""
        try:
            import ctypes
            hwnd = int(self.winId())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ok = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value),
            )
            if ok != 0:
                # Older Windows 10 builds used attribute 19 before the API
                # was finalized as 20 - try that as a fallback rather than
                # silently giving up on any pre-22H2-ish build. Same
                # fallback the popup uses.
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 19, ctypes.byref(value), ctypes.sizeof(value),
                )
        except Exception:
            pass  # non-Windows or older Windows - default title bar stands

    def _apply_initial_size(self):
        self._resize_programmatically(self._ideal_window_width(), 760)
        # Qt's own QLayout::activate() runs as part of the show cycle and
        # recomputes size constraints from the layout tree from scratch --
        # it does this *after* anything set in __init__, so a
        # setMaximumSize() call made before show() (as this used to do)
        # gets silently overwritten the moment the window is actually
        # shown, right back to a Windows/DPI-path-dependent value derived
        # from the fixed-width columns' current sizeHint. That's what was
        # actually locking horizontal/diagonal resizing. Reasserted again
        # in resizeEvent below, since any later relayout can recompute and
        # reapply the same stale constraint, not only the first show.
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)  # Qt's own QWIDGETSIZE_MAX

    def _resize_programmatically(self, width: int, height: int):
        """resize() the window without it being mistaken for a manual
        (user-driven) resize by resizeEvent below."""
        self._resizing_programmatically = True
        try:
            self.resize(width, height)
        finally:
            self._resizing_programmatically = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Belt-and-braces alongside showEvent above: QLayout::activate()
        # can recompute and reapply a stale min/max constraint on any
        # relayout (column add/remove, project switch, Settings change),
        # not just the first show, so it's cleared here too. Cheap
        # (two no-op Qt calls when already unbounded) and idempotent.
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        # Any resize not flagged as our own programmatic call -- i.e. the
        # person dragging an edge/corner, using a maximize/snap gesture,
        # etc. -- means the window's width should no longer be silently
        # overwritten by the "hug content" auto-fit on every reload;
        # explicit column add/remove still re-fits it (see
        # _update_window_width), since that's the documented behavior.
        # Guarded on isVisible(): Qt's layout engine can fire resizeEvent
        # during widget construction/activation before the window is ever
        # shown (e.g. from _build_ui()'s setCentralWidget/layout passes),
        # which is not a user action and must not be mistaken for one --
        # otherwise the very first on-screen appearance could already be
        # (wrongly) treated as "manually resized" and skip the initial
        # content-fit sizing.
        if not self._resizing_programmatically and self.isVisible():
            self._user_resized_width = True
        # Redistribute extra width across columns as the window is resized,
        # instead of leaving newly-revealed width as empty scrollable space
        # off to the right while the board stays pinned at its original
        # (minimum) content width -- debounced via a single-shot timer
        # restarted on every event rather than run synchronously here,
        # since resizeEvent fires once per pixel-delta during a live
        # edge-drag on Windows; recomputing/relaying-out every column on
        # every one of those would be wasted work at best and a visibly
        # janky/blocking drag at worst.
        timer = getattr(self, "_column_stretch_timer", None)
        if timer is not None:
            timer.start(30)
        topbar_timer = getattr(self, "_topbar_scale_timer", None)
        if topbar_timer is not None:
            topbar_timer.start(30)
        toast_host = getattr(self, "_toast_host", None)
        if toast_host is not None:
            toast_host._reposition()

    def closeEvent(self, event):
        """Warn before closing if any project has changes made after its
        last external Save As / Quick Save that haven't been written back
        out to that file (see _external_dirty). The app's own AppData
        autosave (self._save) always keeps the project safe on disk
        regardless -- this is specifically about not silently leaving an
        external .fboard.json file the person explicitly saved to out of
        date with what's on screen, since that file may be the copy they
        actually intend to keep using (share it, back it up, etc.)."""
        if not self.storage.last_save_ok and not self.storage.save():
            choice = QMessageBox.warning(self, "⚠️ Changes not saved",
                "Your latest changes could not be saved. Close and lose these changes?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if choice != QMessageBox.Yes:
                event.ignore()
                return
        dirty_projects = [
            p for p in self.storage.projects if p.id in self._external_dirty
        ]
        if dirty_projects:
            names = ", ".join(f"'{p.name}'" for p in dirty_projects[:5])
            if len(dirty_projects) > 5:
                names += f", and {len(dirty_projects) - 5} more"
            confirm = QMessageBox.question(
                self, "\u26A0\uFE0F Unsaved External Changes",
                "You have changes in " + names + " made since the last "
                "Save As\u2026/Quick Save to file. These changes are safely "
                "stored in WhiteBoard's own data either way, but the "
                "external file(s) you saved won't reflect them unless you "
                "save again.\n\nClose anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                event.ignore()
                return
        reminders = getattr(self, "reminders", None)
        if reminders is not None:
            reminders.stop()
        toast_host = getattr(self, "_toast_host", None)
        if toast_host is not None:
            toast_host.dismiss_all()
        super().closeEvent(event)

    def _mark_external_dirty(self, project_id: str):
        """Called whenever a project actually changes, so closeEvent can
        warn if that change hasn't since been written back to whatever
        external file the project was last Save As/Quick Saved to. A
        project that's never been externally saved this session has
        nothing to flag -- there's no external file to go stale."""
        if project_id in self._last_saved_paths:
            self._external_dirty.add(project_id)

    # ------------------------------------------------------------ undo/redo
    def _focused_widget_wants_native_undo(self) -> bool:
        """True while a text-editing widget (line edit, text edit, combo
        box editor) has focus, so Ctrl+Z/Ctrl+Y is left to Qt's own
        built-in text undo for that widget instead of being intercepted
        by the board-level undo stack -- otherwise, typing into a card
        title/description and pressing Ctrl+Z to fix a typo would instead
        undo the last board action, which would be surprising and could
        discard in-progress edits."""
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QComboBox
        w = QApplication.focusWidget()
        return isinstance(w, (QLineEdit, QTextEdit, QComboBox))

    def _on_undo_shortcut(self):
        if self._focused_widget_wants_native_undo():
            return
        self._undo()

    def _on_redo_shortcut(self):
        if self._focused_widget_wants_native_undo():
            return
        self._redo()

    def _on_delete_shortcut(self):
        if self._focused_widget_wants_native_undo():
            return
        if self._selected_card_ids:
            self._bulk_delete_selected()

    def _push_undo(self, undo_fn, redo_fn, project_id: str):
        """Record one undoable action. undo_fn/redo_fn are zero-arg
        closures that fully restore the project to its pre/post-action
        state (typically by swapping in a deep-copied snapshot of the
        affected columns/cards) -- not incremental deltas, so undo/redo
        stays correct even if intervening actions touched overlapping
        cards/columns. Called by every card/column create/edit/delete/
        move action below, immediately after that action's own _save()/
        refresh. No-op while an undo/redo itself is being applied, so
        stepping through undo/redo history doesn't push new entries onto
        the stack, and clears the redo stack the same way any normal
        editor does once a fresh action is taken after undoing."""
        if self._applying_undo_redo:
            return
        self._undo_stack.append((undo_fn, redo_fn, project_id))
        if len(self._undo_stack) > self._UNDO_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _undo(self):
        if not self._undo_stack:
            self._toast_host.show_toast("Nothing to undo", kind="info", duration_ms=1400)
            return
        undo_fn, redo_fn, project_id = self._undo_stack.pop()
        self._applying_undo_redo = True
        try:
            undo_fn()
        finally:
            self._applying_undo_redo = False
        self._redo_stack.append((undo_fn, redo_fn, project_id))
        self._save(project_id)
        if project_id == self.storage.active_project_id:
            self._load_active_project()
        self._toast_host.show_toast("Undone", kind="info", duration_ms=1400)

    def _redo(self):
        if not self._redo_stack:
            self._toast_host.show_toast("Nothing to redo", kind="info", duration_ms=1400)
            return
        undo_fn, redo_fn, project_id = self._redo_stack.pop()
        self._applying_undo_redo = True
        try:
            redo_fn()
        finally:
            self._applying_undo_redo = False
        self._undo_stack.append((undo_fn, redo_fn, project_id))
        self._save(project_id)
        if project_id == self.storage.active_project_id:
            self._load_active_project()
        self._toast_host.show_toast("Redone", kind="info", duration_ms=1400)

    def _snapshot_project_state(self, project: Project):
        """Deep-copy just the columns+cards of a project, for use as an
        undo/redo restore point. Kept as a small helper since every
        card/column mutation below needs the same before/after pair."""
        return copy.deepcopy(project.columns), copy.deepcopy(project.cards)

    def _make_restore_fn(self, project_id: str, columns, cards):
        """Build a zero-arg closure that restores the given project to
        exactly the given (columns, cards) snapshot. A fresh deep copy is
        applied each call (not the stored snapshot directly), so undoing
        then redoing then undoing again each restores independently
        rather than the project and the stored snapshot ending up as the
        same mutable objects."""
        def _restore():
            project = self.storage.get_project(project_id)
            if project is None:
                return
            project.columns = copy.deepcopy(columns)
            project.cards = copy.deepcopy(cards)
        return _restore

    def _record_undo_step(self, project: Project, before):
        """Common tail of every undoable mutation: given the (columns,
        cards) snapshot captured *before* the mutation ran, capture the
        state *after* and push both onto the undo stack as a matched
        undo/redo pair."""
        before_columns, before_cards = before
        after_columns, after_cards = self._snapshot_project_state(project)
        undo_fn = self._make_restore_fn(project.id, before_columns, before_cards)
        redo_fn = self._make_restore_fn(project.id, after_columns, after_cards)
        self._push_undo(undo_fn, redo_fn, project.id)

    # ---------------------------------------------------------- selection
    def _ordered_visible_card_ids(self):
        return [card.id for widget in self._column_widgets.values()
                for card in widget._sorted_for_display([c for c in widget._all_cards
                    if not widget._type_filter or c.card_type == widget._type_filter])]

    def _on_card_select_requested(self, card_id: str, shift: bool, ctrl: bool):
        project = self.active_project
        if project is None:
            return
        if shift and self._selection_anchor:
            ordered = self._ordered_visible_card_ids()
            try:
                a = ordered.index(self._selection_anchor)
                b = ordered.index(card_id)
            except ValueError:
                # Anchor (or the clicked card) is no longer on the board --
                # fall back to treating this as a plain click rather than
                # raising or silently doing nothing.
                self._selected_card_ids = {card_id}
                self._selection_anchor = card_id
            else:
                lo, hi = (a, b) if a <= b else (b, a)
                self._selected_card_ids = set(ordered[lo:hi + 1])
                # Anchor itself is intentionally NOT moved on a Shift-click
                # (matches standard file-manager/list Shift-select
                # behavior: repeated Shift-clicks all extend from the same
                # original anchor, not from the last click).
        elif ctrl:
            if card_id in self._selected_card_ids:
                self._selected_card_ids.discard(card_id)
            else:
                self._selected_card_ids.add(card_id)
            self._selection_anchor = card_id
        else:
            # Plain click: if this card is the *only* thing selected,
            # clicking it again clears the selection (a quick way to
            # deselect without hunting for empty space) -- otherwise a
            # plain click always resets the selection to just this card.
            if self._selected_card_ids == {card_id}:
                self._selected_card_ids = set()
                self._selection_anchor = None
            else:
                self._selected_card_ids = {card_id}
                self._selection_anchor = card_id
        self._apply_selection_to_columns()

    def _on_card_check_toggled(self, card_id: str, checked: bool):
        """A card's own checkbox (see card_widget.FeatureCardWidget) was
        toggled directly. Unlike Shift/Ctrl-click, a checkbox toggle never
        has range/anchor semantics -- it just adds or removes this one
        card from the selection, leaving every other currently-selected
        card exactly as it was. Sets/keeps the anchor on this card either
        way, so a Shift-click immediately after checking a box extends
        the range from here, matching how the last explicit selection
        action (click or check) is the expected Shift anchor."""
        if checked:
            self._selected_card_ids.add(card_id)
        else:
            self._selected_card_ids.discard(card_id)
        self._selection_anchor = card_id
        self._apply_selection_to_columns()

    def _apply_selection_to_columns(self):
        for cw in self._column_widgets.values():
            cw.set_selected_ids(self._selected_card_ids)
        self._update_selection_bar()
        self.workspace.sync_selection()

    def _clear_selection(self):
        if not self._selected_card_ids:
            return
        self._selected_card_ids = set()
        self._selection_anchor = None
        self._apply_selection_to_columns()

    def _update_selection_bar(self):
        bar = getattr(self, "_selection_bar", None)
        if bar is None:
            return
        count = len(self._selected_card_ids)
        if count:
            self._selection_bar_label.setText(
                f"\u2705 {count} card{'s' if count != 1 else ''} selected"
            )
            bar.show()
        else:
            bar.hide()

    def _selected_cards_by_column(self):
        """Group currently-selected cards by their column id, restricted
        to cards that still exist in the active project -- the common
        shape every bulk action below needs."""
        project = self.active_project
        if project is None:
            return {}, []
        selected = [c for c in project.cards if c.id in self._selected_card_ids]
        by_column = {}
        for c in selected:
            by_column.setdefault(c.column_id, []).append(c.id)
        return by_column, selected

    def _bulk_delete_selected(self):
        project = self.active_project
        if project is None or not self._selected_card_ids:
            return
        _, selected = self._selected_cards_by_column()
        if not selected:
            return
        if self._confirm_deletes_enabled():
            confirm = QMessageBox.question(
                self, "\U0001F5D1\uFE0F Delete Cards",
                f"Delete {len(selected)} selected card{'s' if len(selected) != 1 else ''}?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return
        before = self._snapshot_project_state(project)
        affected_columns = {c.column_id for c in selected}
        remove_ids = {c.id for c in selected}
        project.cards = [c for c in project.cards if c.id not in remove_ids]
        self._selected_card_ids.clear()
        self._selection_anchor = None
        self._save(project.id)
        self._record_undo_step(project, before)
        self._refresh_columns(affected_columns)
        self._update_selection_bar()
        self._toast_host.show_toast(f"Deleted {len(selected)} card{'s' if len(selected) != 1 else ''}", kind="success")

    def _bulk_move_selected(self, target_column_id: str):
        project = self.active_project
        if project is None or not self._selected_card_ids:
            return
        target_column = next((c for c in project.columns if c.id == target_column_id), None)
        if target_column is None:
            return
        _, selected = self._selected_cards_by_column()
        if not selected:
            return
        before = self._snapshot_project_state(project)
        affected_columns = {c.column_id for c in selected} | {target_column_id}
        # Append each moved card to the end of the target column, in the
        # same relative order they already had (by source column then
        # order), so a bulk move has a stable, predictable result rather
        # than depending on dict/set iteration order.
        existing_target = [c for c in project.cards if c.column_id == target_column_id]
        next_order = max([c.order for c in existing_target], default=-1) + 1
        selected_sorted = sorted(selected, key=lambda c: (c.column_id, c.order))
        now = time.time()
        for c in selected_sorted:
            c.column_id = target_column_id
            c.order = next_order
            c.updated_at = now
            next_order += 1
        self._save(project.id)
        self._record_undo_step(project, before)
        self._refresh_columns(affected_columns)
        self._toast_host.show_toast(
            f"Moved {len(selected)} card{'s' if len(selected) != 1 else ''} to '{target_column.name}'",
            kind="success",
        )

    def _bulk_change_type_selected(self, new_type: str):
        project = self.active_project
        if project is None or not self._selected_card_ids or not new_type:
            return
        _, selected = self._selected_cards_by_column()
        if not selected:
            return
        before = self._snapshot_project_state(project)
        affected_columns = {c.column_id for c in selected}
        now = time.time()
        for c in selected:
            c.card_type = new_type
            c.updated_at = now
        self._save(project.id)
        self._record_undo_step(project, before)
        self._refresh_columns(affected_columns)
        self._toast_host.show_toast(
            f"Changed {len(selected)} card{'s' if len(selected) != 1 else ''} to '{new_type}'",
            kind="success",
        )

    def _bulk_change_priority_selected(self, new_priority: str):
        """Bulk-action bar > Set priority(ies)\u2026: apply one priority
        level (or "" to clear it) to every currently-selected card, in one
        undoable step. Mirrors _bulk_change_type_selected exactly, just
        for card.priority instead of card.card_type."""
        project = self.active_project
        if project is None or not self._selected_card_ids:
            return
        _, selected = self._selected_cards_by_column()
        if not selected:
            return
        before = self._snapshot_project_state(project)
        affected_columns = {c.column_id for c in selected}
        now = time.time()
        for c in selected:
            c.priority = new_priority
            c.updated_at = now
        self._save(project.id)
        self._record_undo_step(project, before)
        self._refresh_columns(affected_columns)
        label = priority_label(new_priority) if new_priority else "No priority"
        self._toast_host.show_toast(
            f"Set {len(selected)} card{'s' if len(selected) != 1 else ''} to '{label}'",
            kind="success",
        )

    def _bulk_duplicate_selected(self):
        """Bulk-action bar > Duplicate: insert a copy of every selected
        card directly after its original in the same column, same as the
        single-card Duplicate action (see _on_duplicate_card) but applied
        to the whole selection at once in a single undoable step. The
        new copies become the active selection afterward, matching how a
        duplicate is usually meant to be immediately actionable (move it,
        retype it, etc.) rather than leaving the originals selected."""
        project = self.active_project
        if project is None or not self._selected_card_ids:
            return
        _, selected = self._selected_cards_by_column()
        if not selected:
            return
        before = self._snapshot_project_state(project)
        affected_columns = {c.column_id for c in selected}
        now = time.time()
        new_ids = set()
        # Process one column at a time so each column's order-shifting
        # (see _on_duplicate_card's own single-card version of this) stays
        # correct even when several selected cards in the same column are
        # being duplicated together -- duplicating in descending order of
        # original order within each column means each already-inserted
        # duplicate's own order never needs to be shifted again by a
        # later duplicate in the same column.
        selected_by_column = {}
        for c in selected:
            selected_by_column.setdefault(c.column_id, []).append(c)
        for column_id, cards_in_column in selected_by_column.items():
            for original in sorted(cards_in_column, key=lambda c: c.order, reverse=True):
                for c in project.cards:
                    if c.column_id == column_id and c.order > original.order:
                        c.order += 1
                new_card = copy.deepcopy(original)
                new_card.id = new_id()
                new_card.order = original.order + 1
                new_card.created_at = now
                new_card.updated_at = now
                project.cards.append(new_card)
                new_ids.add(new_card.id)
        self._save(project.id)
        self._record_undo_step(project, before)
        self._selected_card_ids = new_ids
        self._selection_anchor = None
        self._refresh_columns(affected_columns)
        self._toast_host.show_toast(
            f"Duplicated {len(selected)} card{'s' if len(selected) != 1 else ''}",
            kind="success",
        )

    def _on_selection_move_clicked(self):
        project = self.active_project
        if project is None or not self._selected_card_ids:
            return
        menu = QMenu(self)
        for column in sorted(project.columns, key=lambda c: c.order):
            action = menu.addAction(column.name)
            action.triggered.connect(lambda checked=False, cid=column.id: self._bulk_move_selected(cid))
        menu.exec(self._selection_move_btn.mapToGlobal(self._selection_move_btn.rect().bottomLeft()))

    def _on_selection_type_clicked(self):
        if not self._selected_card_ids:
            return
        menu = QMenu(self)
        for t in self._available_card_types():
            action = menu.addAction(t)
            action.triggered.connect(lambda checked=False, tt=t: self._bulk_change_type_selected(tt))
        menu.exec(self._selection_type_btn.mapToGlobal(self._selection_type_btn.rect().bottomLeft()))

    def _on_selection_priority_clicked(self):
        if not self._selected_card_ids:
            return
        menu = QMenu(self)
        none_action = menu.addAction("\u2014 None \u2014")
        none_action.triggered.connect(lambda checked=False: self._bulk_change_priority_selected(""))
        for level in PRIORITY_LEVELS:
            action = menu.addAction(priority_label(level))
            action.triggered.connect(lambda checked=False, lv=level: self._bulk_change_priority_selected(lv))
        menu.exec(self._selection_priority_btn.mapToGlobal(self._selection_priority_btn.rect().bottomLeft()))

    def _on_selection_duplicate_clicked(self):
        self._bulk_duplicate_selected()

    def _on_selection_delete_clicked(self):
        self._bulk_delete_selected()

    def _on_selection_clear_clicked(self):
        self._clear_selection()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar. Every control (title, project selector, buttons, gear)
        # scales down together as the window narrows -- font size shrinks
        # within a bounded range (see _apply_topbar_scale), which in turn
        # shrinks each button/label's own sizeHint, so the whole row keeps
        # fitting without any control being clipped or scrolled out of
        # view. Scaling back up as the window widens is the same code path
        # in reverse. The row still sits inside a frameless QScrollArea as
        # a last-resort safety net (only engages if the row can't fit even
        # at the smallest allowed scale, e.g. an extremely narrow window),
        # not as the primary way narrow widths are handled. The vertical
        # scrollbar is always off since the bar is a single fixed-height
        # row.
        top_bar_scroll = QScrollArea()
        top_bar_scroll.setObjectName("TopBarScroll")
        top_bar_scroll.setWidgetResizable(True)
        top_bar_scroll.setFixedHeight(TOPBAR_HEIGHT)
        top_bar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        top_bar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        top_bar_scroll.setFrameShape(QFrame.NoFrame)

        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(TOPBAR_HEIGHT)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 8, 16, 8)
        top_layout.setSpacing(4)

        title = QLabel("\U0001F4CB WhiteBoard")
        title.setObjectName("AppTitle")
        top_layout.addWidget(title)

        top_layout.addStretch(1)

        self.project_selector = FitPopupComboBox()
        self.project_selector.setObjectName("ProjectSelector")
        self.project_selector.currentIndexChanged.connect(self._on_project_selected)
        top_layout.addWidget(self.project_selector)

        new_project_btn = QPushButton("\u2795 New Project")
        new_project_btn.setToolTip("Start a fresh project with default columns")
        new_project_btn.setCursor(Qt.PointingHandCursor)
        new_project_btn.clicked.connect(self._on_new_project)
        top_layout.addWidget(new_project_btn)

        rename_project_btn = QPushButton("\u270F\uFE0F Rename")
        rename_project_btn.setToolTip("Rename the current project")
        rename_project_btn.setCursor(Qt.PointingHandCursor)
        rename_project_btn.clicked.connect(self._on_rename_project)
        top_layout.addWidget(rename_project_btn)

        delete_project_btn = QPushButton("\U0001F5D1\uFE0F Delete Project")
        delete_project_btn.setObjectName("DangerButton")
        delete_project_btn.setToolTip("Delete the current project and all its cards")
        delete_project_btn.setCursor(Qt.PointingHandCursor)
        delete_project_btn.clicked.connect(self._on_delete_project)
        top_layout.addWidget(delete_project_btn)

        top_layout.addStretch(1)

        open_btn = QPushButton("\U0001F4C2 Open\u2026")
        open_btn.setToolTip("Open a WhiteBoard project file (.fboard.json)")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self._on_open_file)
        top_layout.addWidget(open_btn)

        quick_save_btn = QPushButton("\u26A1 Quick Save")
        quick_save_btn.setToolTip(
            "Save the current project back to its last file location "
            "(prompts for a location the first time, like Save As)"
        )
        quick_save_btn.setCursor(Qt.PointingHandCursor)
        quick_save_btn.clicked.connect(self._on_quick_save_file)
        top_layout.addWidget(quick_save_btn)

        save_btn = QPushButton("\U0001F4BE Save As\u2026")
        save_btn.setToolTip("Save the current project to a new or different file")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._on_save_file)
        top_layout.addWidget(save_btn)

        import_btn = QPushButton("\U0001F4E5 Import\u2026")
        import_btn.setToolTip("Import a project file as a new project")
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.clicked.connect(self._on_import_file)
        top_layout.addWidget(import_btn)

        export_btn = QPushButton("\U0001F4C4 Export\u2026")
        export_btn.setToolTip("Export the current project as a Markdown or plain-text file")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._on_export_file)
        top_layout.addWidget(export_btn)

        # Expanding stretch (not a fixed addSpacing) between every logical
        # button group in this row: with #TopBarScroll's widget resizable
        # to the viewport (see setWidgetResizable(True) below), the extra
        # width the row gains as the window widens/maximizes is now shared
        # out evenly across all the group gaps instead of collecting in
        # just one of them -- previously only the gap before Add Column
        # used addStretch(), so on a wide window every other button sat
        # packed together on the left while a single wide gap opened up
        # right before Add Column. Each stretch has equal weight (1), so
        # widening the window grows every gap by the same amount, keeping
        # the whole row evenly spaced instead of lopsided. Each button
        # still keeps its own Fixed size policy (set below), so widening
        # never stretches a button itself -- only the gaps between groups.
        top_layout.addStretch(1)

        add_column_btn = QPushButton("\u2795 Add Column")
        add_column_btn.setToolTip("Add a new status column to this board")
        add_column_btn.setCursor(Qt.PointingHandCursor)
        add_column_btn.clicked.connect(self._on_add_column)
        top_layout.addWidget(add_column_btn)

        add_card_btn = QPushButton("\u2795 New Card")
        add_card_btn.setObjectName("PrimaryButton")
        add_card_btn.setToolTip("Add a new card to the first column")
        add_card_btn.setCursor(Qt.PointingHandCursor)
        add_card_btn.clicked.connect(self._on_new_card_default)
        top_layout.addWidget(add_card_btn)

        # Same even-spacing stretch as the other group gaps above, so
        # Settings doesn't sit flush against New Card while all the other
        # gaps in the row grow with window width.
        top_layout.addStretch(1)

        settings_btn = QToolButton()
        settings_btn.setObjectName("IconButton")
        settings_btn.setText("\u2699\uFE0F Settings")  # gear + label
        settings_btn.setToolTip("\u2699\uFE0F Settings")
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.clicked.connect(self._on_open_settings)
        top_layout.addWidget(settings_btn)

        # Every direct top-bar control keeps its own natural sizeHint as
        # its size *policy* (Fixed/Fixed: never stretched/compressed by
        # the layout itself) while still being free to report a smaller
        # sizeHint once its effective font size shrinks -- see
        # _apply_topbar_scale below, which changes the font size, not the
        # policy. Without Fixed here, Qt's HBoxLayout can compress/clip
        # buttons directly instead of respecting the scaled-down
        # sizeHint cleanly.
        for i in range(top_layout.count()):
            item = top_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Base (100%-scale) sizes are captured by
        # _topbar_capture_base_sizes() below (also re-run from
        # _apply_theme, since toggling "Larger text" changes what 100%
        # actually is for every control here).
        self._top_bar_widget = top_bar
        self._top_bar_scroll = top_bar_scroll
        self._topbar_icon_buttons = [settings_btn]
        self._topbar_icon_button_base_dim = 28  # matches #IconButton's min-width/min-height in styles.py
        self._topbar_capture_base_sizes()

        top_bar_scroll.setWidget(top_bar)
        root.addWidget(top_bar_scroll)

        # Multi-select bulk-action bar: hidden whenever nothing is
        # selected (the common case), shown just below the top bar the
        # moment a card is selected via Shift/Ctrl-click. A second row
        # rather than folded into the top bar itself, since it only ever
        # applies to the current selection and its available actions
        # (which column to move to, which type to set) depend on the
        # active project's own columns/types, unlike the top bar's always-
        # available actions.
        self._selection_bar = QFrame()
        self._selection_bar.setObjectName("SelectionBar")
        sel_outer = QVBoxLayout(self._selection_bar)
        sel_outer.setContentsMargins(16, 8, 16, 8)
        sel_outer.setSpacing(4)
        self._selection_bar_label = QLabel("")
        self._selection_bar_label.setObjectName("SelectionBarLabel")
        sel_outer.addWidget(self._selection_bar_label)

        # Buttons live in their own FlowLayout row (see FlowLayout above)
        # so they wrap onto additional rows on a narrow window instead of
        # being clipped -- the label stays on its own line above so it's
        # always fully readable regardless of how many rows the buttons
        # wrap to.
        sel_buttons_host = QWidget()
        sel_layout = FlowLayout(sel_buttons_host, margin=0, spacing=8)
        sel_outer.addWidget(sel_buttons_host)

        # Fixed height for the three action buttons below: QSS max-height
        # isn't reliably honored against QPushButton's own sizeHint in Qt,
        # so left unset these buttons' painted/hit rectangle could grow
        # taller than their visible content (bold text + emoji) actually
        # needs -- pinning it in code keeps their box snug and consistent
        # with the rest of the app's buttons.
        SELECTION_BTN_HEIGHT = 31

        self._selection_move_btn = QPushButton("\U0001F5C2\uFE0F Move to\u2026")
        self._selection_move_btn.setToolTip("Move every selected card to another column")
        self._selection_move_btn.setCursor(Qt.PointingHandCursor)
        self._selection_move_btn.setFixedHeight(SELECTION_BTN_HEIGHT)
        self._selection_move_btn.clicked.connect(self._on_selection_move_clicked)
        sel_layout.addWidget(self._selection_move_btn)

        self._selection_type_btn = QPushButton("\U0001F3F7\uFE0F Set type\u2026")
        self._selection_type_btn.setToolTip("Change the type of every selected card")
        self._selection_type_btn.setCursor(Qt.PointingHandCursor)
        self._selection_type_btn.setFixedHeight(SELECTION_BTN_HEIGHT)
        self._selection_type_btn.clicked.connect(self._on_selection_type_clicked)
        sel_layout.addWidget(self._selection_type_btn)

        self._selection_priority_btn = QPushButton("\U0001F6A9 Set priority\u2026")
        self._selection_priority_btn.setToolTip("Change the priority of every selected card")
        self._selection_priority_btn.setCursor(Qt.PointingHandCursor)
        self._selection_priority_btn.setFixedHeight(SELECTION_BTN_HEIGHT)
        self._selection_priority_btn.clicked.connect(self._on_selection_priority_clicked)
        sel_layout.addWidget(self._selection_priority_btn)

        self._selection_duplicate_btn = QPushButton("\U0001F4CB Duplicate")
        self._selection_duplicate_btn.setToolTip("Duplicate every selected card")
        self._selection_duplicate_btn.setCursor(Qt.PointingHandCursor)
        self._selection_duplicate_btn.setFixedHeight(SELECTION_BTN_HEIGHT)
        self._selection_duplicate_btn.clicked.connect(self._on_selection_duplicate_clicked)
        sel_layout.addWidget(self._selection_duplicate_btn)

        self._selection_delete_btn = QPushButton("\U0001F5D1\uFE0F Delete")
        self._selection_delete_btn.setObjectName("DangerButton")
        self._selection_delete_btn.setToolTip("Delete every selected card")
        self._selection_delete_btn.setCursor(Qt.PointingHandCursor)
        self._selection_delete_btn.setFixedHeight(SELECTION_BTN_HEIGHT)
        self._selection_delete_btn.clicked.connect(self._on_selection_delete_clicked)
        sel_layout.addWidget(self._selection_delete_btn)

        self._selection_clear_btn = QToolButton()
        self._selection_clear_btn.setText("\u2715")
        self._selection_clear_btn.setToolTip("Clear selection")
        self._selection_clear_btn.setCursor(Qt.PointingHandCursor)
        self._selection_clear_btn.clicked.connect(self._on_selection_clear_clicked)
        sel_layout.addWidget(self._selection_clear_btn)

        self._selection_bar.hide()
        root.addWidget(self._selection_bar)

        # Board scroll area (smooth horizontal scrolling, unless the user
        # has turned on "Reduce motion" in Settings > Accessibility)
        self.scroll_area = SmoothScrollArea(reduced_motion=self.storage.get_setting("reduced_motion", False))
        self.scroll_area.setObjectName("BoardScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Unlike the QSS "border: none" on #BoardScrollArea (which only
        # zeroes the *painted* border color/width), QFrame still reserves
        # actual layout space for its frame per frameWidth() unless the
        # frame shape itself is set to NoFrame -- matching the inner
        # per-column scroll areas (see column_widget.ColumnWidget), which
        # already do this. Left unset, that reserved sliver plus the
        # unrelated flat "+24" fudge previously added in
        # _ideal_window_width() combined into visible dead space on the
        # right of the window that didn't correspond to anything real.
        self.scroll_area.setFrameShape(QFrame.NoFrame)

        self.board_canvas = QWidget()
        self.board_canvas.setObjectName("BoardCanvas")
        self.board_layout = QHBoxLayout(self.board_canvas)
        self.board_layout.setContentsMargins(BOARD_MARGIN, BOARD_MARGIN, BOARD_MARGIN, BOARD_MARGIN)
        self.board_layout.setSpacing(BOARD_SPACING)
        self.board_layout.addStretch()

        self.scroll_area.setWidget(self.board_canvas)
        self.workspace = WorkspacePanel(self, self.scroll_area)
        root.addWidget(self.workspace, 1)
        self._save_status_label = QLabel("💾 Saved locally · Works offline")
        self._save_status_label.setTextFormat(Qt.PlainText)
        self._save_status_label.setAccessibleName("Save status")
        root.addWidget(self._save_status_label)
        self.storage.save_status_handler = self._show_save_status


    def _topbar_capture_base_sizes(self):
        """(Re-)captures each top-bar widget's natural (100%-scale) pixel
        font size, as a baseline _apply_topbar_scale computes every later
        shrink/grow from. Object names with their own explicit font-size
        in styles.py (#AppTitle, #IconButton) get that value; everything
        else falls back to QWidget's base font-size. The base, the
        #IconButton value, and the fallback each bump by +2px while
        Settings > Accessibility > "Larger text" is on, matching the
        +2px/+2px large_text stylesheet additions in _apply_theme --
        capturing a stale (normal-text) baseline here while large_text was
        on would otherwise make the very first rescale silently shrink the
        toolbar back down to normal size, fighting the accessibility
        setting instead of respecting it. Safe
        to call before the top bar has been built (e.g. from __init__'s
        initial _apply_theme, which runs before _build_ui): the top-bar
        widget list is simply empty at that point, so this becomes a
        no-op until _build_ui calls it again with real widgets."""
        top_bar = getattr(self, "_top_bar_widget", None)
        if top_bar is None:
            return
        layout = top_bar.layout()
        if layout is None:
            return
        large_text = self.storage.get_setting("large_text", False)
        try:
            ui_scale_pct = int(self.storage.get_setting("ui_scale", 100))
        except (TypeError, ValueError):
            ui_scale_pct = 100
        ui_scale_factor = max(80, min(150, ui_scale_pct)) / 100.0
        # Base sizes here must track styles.py's own defaults for these
        # selectors (QWidget 14px, #AppTitle 17px, #IconButton 19px) plus
        # _apply_theme's large-text +2px overrides on top of each, further
        # multiplied by ui_scale_factor -- a baseline that doesn't match
        # what the stylesheet actually applied would make the very first
        # rescale silently shrink/grow the toolbar to the wrong "100%"
        # instead of the size it's really rendering at.
        base_default = round((16 if large_text else 14) * ui_scale_factor)
        base_title = round((19 if large_text else 17) * ui_scale_factor)  # #AppTitle
        base_icon_button = round((21 if large_text else 19) * ui_scale_factor)  # #IconButton
        base_default = max(9, base_default)
        base_title = max(9, base_title)
        base_icon_button = max(9, base_icon_button)
        _TOPBAR_BASE_PX = {"AppTitle": base_title, "IconButton": base_icon_button}
        self._topbar_base_point_sizes = {}
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None:
                self._topbar_base_point_sizes[w] = _TOPBAR_BASE_PX.get(w.objectName(), base_default)
        self._topbar_project_selector_base_min_width = self._compute_project_selector_min_width()
        # Baselines changed (e.g. large_text was just toggled) - the
        # cached scale factor no longer describes the widgets' current
        # on-screen state relative to the new baseline, so force the next
        # _apply_topbar_scale call to actually recompute and re-apply
        # rather than short-circuiting on "factor looks unchanged".
        self._topbar_scale_factor = 1.0

    def _compute_project_selector_min_width(self) -> int:
        """#ProjectSelector's min-width used to be a flat 170px regardless
        of the actual project name(s) loaded, which left a visible gap of
        dead space inside the closed field itself whenever every project
        name was shorter than that -- distinct from (and not fixed by)
        FitPopupComboBox above, which only fits the *open popup*, not the
        closed field. This instead measures the widest currently-loaded
        project name (falling back to a small floor if there are no
        projects yet, e.g. during initial startup before _build_ui has
        created the selector) and adds the same chrome the field itself
        paints around its text: the dropdown arrow box, left/right
        padding, and border (see #ProjectSelector in styles.py), plus a
        little breathing room so the text never sits flush against the
        arrow or border."""
        selector = getattr(self, "project_selector", None)
        widest = 0
        if selector is not None:
            fm = QFontMetrics(selector.font())
            for i in range(selector.count()):
                w = fm.horizontalAdvance(selector.itemText(i))
                if w > widest:
                    widest = w
        # 22px drop-down arrow box + ~20px left/right padding/border chrome
        # (see #ProjectSelector in styles.py) + 12px breathing room.
        CHROME = 54
        MIN_FLOOR = 90
        MAX_CEILING = 260
        return max(MIN_FLOOR, min(MAX_CEILING, widest + CHROME))

    # ---------------------------------------------------------------- theme
    def _apply_theme(self, theme_id: str):
        app = QApplication.instance()
        focus_outlines = self.storage.get_setting("focus_outlines", True)
        large_text = self.storage.get_setting("large_text", False)
        larger_click_targets = self.storage.get_setting("larger_click_targets", False)
        # UI scale / zoom (Settings > Accessibility): a continuous 80-150%
        # factor applied on top of whatever base size "large_text" above
        # already produced. 100 is a no-op (every existing install with
        # no ui_scale setting yet defaults to 100 -- see
        # storage.DEFAULT_SETTINGS -- and renders identically to before
        # this setting existed). Clamped defensively in case a hand-edited
        # settings file has an out-of-range or non-numeric value.
        try:
            ui_scale_pct = int(self.storage.get_setting("ui_scale", 100))
        except (TypeError, ValueError):
            ui_scale_pct = 100
        ui_scale_pct = max(80, min(150, ui_scale_pct))
        ui_scale_factor = ui_scale_pct / 100.0
        # Skip rebuilding/reapplying the whole app-wide stylesheet -- by
        # far the most expensive part of a theme switch, since
        # QApplication.setStyleSheet() triggers a full style
        # recomputation across every widget in the app -- when nothing
        # about the effective theme has actually changed since the last
        # call. This is the common case for rapid repeats: clicking the
        # same swatch twice in Settings' live preview, or Cancel
        # reverting to a theme that's already the one being previewed.
        # Guarded on app.styleSheet() too so the very first call (from
        # __init__, before any stylesheet has ever been applied) always
        # goes through even if the cache key coincidentally matches the
        # (unset) default.
        ui_font = self.storage.get_setting("ui_font", "SF Pro Text")
        reader_size = self.storage.get_setting("reader_font_size", 12)
        cache_key = (theme_id, focus_outlines, large_text, larger_click_targets, ui_scale_pct, ui_font, reader_size)
        if app is not None and app.styleSheet() and getattr(self, "_last_applied_theme_key", None) == cache_key:
            return
        self._last_applied_theme_key = cache_key
        from card_widget import FeatureCardWidget
        FeatureCardWidget.focus_outlines = focus_outlines
        FeatureCardWidget.oled_mode = theme_id.startswith("oled_")
        FeatureCardWidget.focus_color = styles.theme_colors(theme_id)["accent"]
        toast_host = getattr(self, "_toast_host", None)
        if toast_host is not None:
            toast_host.set_theme(theme_id)
        if app is not None:
            sheet = styles.build_stylesheet(
                theme_id, focus_outlines=focus_outlines, larger_click_targets=larger_click_targets,
            )
            # Base (100%-scale) sizes for the selector-specific overrides
            # below, before ui_scale_factor is applied. These must stay in
            # lockstep with styles.py's own defaults (14/17/19/14) --
            # large_text simply picks a different starting baseline
            # (16/19/21/16) for ui_scale_factor to then multiply, so
            # "Larger text" and "UI scale" combine instead of one
            # silently overriding the other.
            if large_text:
                base_widget, base_title, base_icon, base_header = 16, 19, 21, 16
            else:
                base_widget, base_title, base_icon, base_header = 14, 17, 19, 14
            # Apply ui_scale_factor on top of whichever baseline was
            # picked above. At the default ui_scale_factor == 1.0 this is
            # a no-op when large_text is also off (base_widget stays the
            # stylesheet's own built-in 14px, so no override is even
            # emitted), preserving pixel-identical output for every
            # existing install that predates this setting.
            if large_text or abs(ui_scale_factor - 1.0) > 0.001:
                sheet += (
                    f"\nQWidget {{ font-size: {max(9, round(base_widget * ui_scale_factor))}px; }}"
                    f"\n#AppTitle {{ font-size: {max(9, round(base_title * ui_scale_factor))}px; }}"
                    f"\n#IconButton {{ font-size: {max(9, round(base_icon * ui_scale_factor))}px; }}"
                    f"\n#ColumnHeader {{ font-size: {max(9, round(base_header * ui_scale_factor))}px; }}\n"
                )
            font_family = ui_font.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", " ").replace("\r", " ")
            sheet += f'\nQWidget, #AppTitle, #ColumnHeader, #ChangelogVersion, #ColumnEmptyStateIcon {{ font-family: "{font_family}", "Segoe UI", sans-serif; }}'
            sheet += f'\n#CardDesc {{ font-size: {round(reader_size * ui_scale_factor)}pt; }}'
            app.setStyleSheet(sheet)
        for column in getattr(self, "_column_widgets", {}).values():
            column._apply_accent_color()
            for card_widget in column._card_widgets.values():
                card_widget._apply_selection_frame()
                card_widget._apply_shadow()
        # Re-derive the top bar's scaling baseline against the stylesheet
        # that was just applied (large_text/ui_scale may have just changed
        # what "100%" means for every control here) and immediately re-fit
        # the row to the window's current width against that new baseline.
        # No-ops safely if the top bar hasn't been built yet (the very
        # first call, from __init__, runs before _build_ui).
        self._topbar_capture_base_sizes()
        self._apply_topbar_scale()
        workspace = getattr(self, "workspace", None)
        if workspace is not None:
            workspace.fit_toolbar()

    # ------------------------------------------------------------- project
    def _ensure_project_exists(self):
        if not self.storage.projects:
            p = Project.new_default("My Project")
            self.storage.add_project(p)

    def _refresh_project_selector(self):
        self.project_selector.blockSignals(True)
        self.project_selector.clear()
        # Alphabetical order (case-insensitive) in the project dropdown.
        sorted_projects = sorted(self.storage.projects, key=lambda p: p.name.casefold())
        for p in sorted_projects:
            self.project_selector.addItem(p.name, p.id)
        active_index = 0
        for i, p in enumerate(sorted_projects):
            if p.id == self.storage.active_project_id:
                active_index = i
                break
        self.project_selector.setCurrentIndex(active_index)
        # Every item in the open popup already renders bold (see
        # #ProjectSelector QAbstractItemView in styles.py), which covers
        # the closed field always showing the active project's name in
        # bold -- but with every row already bold, the active project
        # can't actually be picked out from the others once the popup is
        # open. An explicit extra-bold QFont on just that one row's item
        # data (Qt.FontRole) makes the active project distinguishable in
        # the open list too, without touching the QSS rule every other
        # item still relies on for its own (normal-strength) bold.
        active_font = self.project_selector.font()
        active_font.setBold(True)
        active_font.setWeight(QFont.ExtraBold)
        for i in range(self.project_selector.count()):
            self.project_selector.setItemData(
                i, active_font if i == active_index else None, Qt.FontRole
            )
        self.project_selector.blockSignals(False)

        # Re-derive the closed field's own min-width against the project
        # names that were just loaded (see _compute_project_selector_min_width)
        # and re-apply it immediately -- not just left for the next resize
        # to pick up via _apply_topbar_scale, since that call short-circuits
        # when the window's width factor hasn't changed, which is the
        # common case here (switching/renaming/adding a project doesn't
        # resize the window).
        if hasattr(self, "_topbar_base_point_sizes"):
            self._topbar_project_selector_base_min_width = self._compute_project_selector_min_width()
            factor = getattr(self, "_topbar_scale_factor", 1.0) or 1.0
            scaled_min_w = max(90, round(self._topbar_project_selector_base_min_width * factor))
            base_sizes = getattr(self, "_topbar_base_point_sizes", {})
            selector_base_px = base_sizes.get(self.project_selector, 14)
            scaled_px = max(9, round(selector_base_px * factor))
            self.project_selector.setStyleSheet(f"font-size: {scaled_px}px; min-width: {scaled_min_w}px;")

    @property
    def active_project(self) -> Project:
        return self.storage.get_project(self.storage.active_project_id)

    def _save(self, project_id: str = None):
        """Persist via storage and tell the user if it failed (disk full,
        permission denied, etc.) instead of letting the original unguarded
        call silently lose the change or, worse, let an uncaught OSError
        escape this Qt slot and crash the app. Every direct storage-save
        call in this file goes through here so the one guard covers every
        add/edit/delete/reorder/settings action without changing what
        happens on the (overwhelmingly common) success path.

        project_id: when the caller knows exactly which project just
        changed (the overwhelmingly common case -- almost every card/
        column mutation only ever touches the active project), this
        writes just that project's file plus the small index, instead of
        checking every loaded project's content hash. Falls back to a
        full storage.save() when omitted (e.g. after a project delete,
        where more than one project's on-disk state may need updating)."""
        ok = self.storage.save_project(project_id) if project_id else self.storage.save()
        # Flag whichever project(s) just changed as having external-file
        # changes pending, so closeEvent can warn if the person saved a
        # copy to disk earlier this session and hasn't re-saved since.
        # project_id is the common case (a targeted single-project save);
        # a full-storage save (project_id omitted, e.g. after a project
        # delete) can't cheaply tell which project(s) actually changed
        # content, so it conservatively flags every currently-loaded
        # project that has an external save target at all.
        if project_id:
            self._mark_external_dirty(project_id)
        else:
            for pid in list(self._last_saved_paths.keys()):
                self._mark_external_dirty(pid)

    def _show_save_status(self, ok):
        self._save_status_label.setText("💾 Saved locally · Works offline" if ok else "⚠️ Changes not saved — check disk space and permissions")
        if not ok:
            error_log.log_error("Save to app data directory failed")
            self._toast_host.show_toast("Could not save. Keep the app open and check disk space and permissions.", kind="error", duration_ms=6000)

    def _on_project_selected(self, index):
        if index < 0:
            return
        project_id = self.project_selector.itemData(index)
        if project_id and project_id != self.storage.active_project_id:
            self.storage.active_project_id = project_id
            self._save()
            self._load_active_project()

    def _on_new_project(self):
        dialog = NewProjectDialog(self)
        if dialog.exec():
            values = dialog.get_values()
            p = Project.new_default(values["name"], column_names=values["columns"])
            self.storage.add_project(p)
            self._refresh_project_selector()
            self._load_active_project()

    def _on_rename_project(self):
        project = self.active_project
        if not project:
            return
        dialog = TextPromptDialog(self, heading="\u270F\uFE0F Rename Project", label="Project name", initial=project.name)
        if dialog.exec():
            new_name = dialog.get_value()
            self.storage.rename_project(project.id, new_name)
            self._refresh_project_selector()

    def _on_delete_project(self):
        project = self.active_project
        if not project:
            return
        confirm = QMessageBox.question(
            self, "\U0001F5D1\uFE0F Delete Project",
            f"Delete project '{project.name}' and all its cards?\nThis can't be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.storage.delete_project(project.id)
            self._external_dirty.discard(project.id)
            self._column_sort_state.pop(project.id, None)
            if self._last_saved_paths.pop(project.id, None) is not None:
                self.storage.set_setting("last_saved_paths", dict(self._last_saved_paths))
            self._ensure_project_exists()
            self._refresh_project_selector()
            self._load_active_project()

    # --------------------------------------------------------- file I/O
    # Open/Save load or write a single project as a standalone JSON file
    # (using the same Project.to_dict/from_dict shape already used for the
    # main data file), independent of the app's own AppData storage.
    # Import loads a file the same way but always adds it as a new project
    # instead of replacing the active one, so importing never risks losing
    # unsaved local state.
    FILE_FILTER = "WhiteBoard Project (*.fboard.json);;JSON files (*.json);;All files (*)"

    def _default_export_filename(self, project: Project) -> str:
        safe = "".join(c if (c.isalnum() or c in " -_") else "_" for c in project.name).strip() or "project"
        return f"{safe}.fboard.json"

    def _write_project_file(self, project: Project, path: str) -> bool:
        """Shared write path for Save As and Quick Save. Returns True on
        success; shows the same error dialog either way on failure so both
        actions fail the same, visible way rather than one of them
        silently losing the write."""
        try:
            atomic_write_json(path, self.storage.attachments.export_project(project))
            return True
        except (OSError, ValueError) as e:
            error_log.log_error("Save As / Quick Save to external file", e)
            self._toast_host.show_toast(
                f"Couldn't save the project file: {e}", kind="error", duration_ms=4500,
            )
            return False

    def _on_save_file(self):
        """Save As\u2026: always prompts for a location, and remembers it as
        this project's Quick Save target going forward."""
        project = self.active_project
        if not project:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", self._default_export_filename(project), self.FILE_FILTER
        )
        if not path:
            return
        if self._write_project_file(project, path):
            self._last_saved_paths[project.id] = path
            self._external_dirty.discard(project.id)
            self.storage.set_setting("last_saved_paths", dict(self._last_saved_paths))
            self._toast_host.show_toast(f"Saved '{project.name}'", kind="success")

    def _on_quick_save_file(self):
        """Quick Save: re-saves the current project straight back to
        wherever it was last saved (Save As, or a previous Quick Save) in
        this session, with no dialog. If this project has never been
        saved to a file yet this session, there's nowhere to "quick" save
        to, so this falls back to the same prompt Save As shows -- and
        remembers the chosen location the same way, so the next Quick
        Save has a target."""
        project = self.active_project
        if not project:
            return
        path = self._last_saved_paths.get(project.id)
        if not path:
            self._on_save_file()
            return
        if self._write_project_file(project, path):
            self._external_dirty.discard(project.id)
            self._toast_host.show_toast(f"Saved '{project.name}'", kind="success")

    def _read_project_file(self, path: str) -> Project:
        """Load and validate a project file. Raises ValueError with a
        user-facing message on any problem, so callers can show it directly
        instead of leaking a raw exception/traceback."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            raise ValueError("That file isn't valid JSON.")
        except OSError as e:
            raise ValueError(f"Could not read the file:\n{e}")
        if not isinstance(data, dict) or "columns" not in data or "cards" not in data:
            raise ValueError("That file doesn't look like a WhiteBoard project.")
        try:
            project = Project.from_dict(data)
            self.storage.attachments.import_project(project, data.get("attachment_files"))
            return project
        except (TypeError, AttributeError, ValueError, OSError) as error:
            raise ValueError(f"Could not open the project: {error}")

    def _on_open_file(self):
        """Open a project file and switch to it. If it matches a project
        already in the library (by id), that existing project is made
        active rather than creating a duplicate; otherwise it's added as a
        new project, same as Import."""
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", self.FILE_FILTER)
        if not path:
            return
        try:
            project = self._read_project_file(path)
        except ValueError as e:
            error_log.log_error("Open project file", e)
            self._toast_host.show_toast(str(e), kind="error", duration_ms=4500)
            return
        existing = self.storage.get_project(project.id)
        if existing is not None:
            self.storage.active_project_id = existing.id
            self._save()
        else:
            self.storage.add_project(project)
        self._refresh_project_selector()
        self._load_active_project()
        self._toast_host.show_toast(f"Opened '{project.name}'", kind="success")

    def _on_import_file(self):
        """Import a project file as a brand-new project (a fresh id), so
        importing the same file twice -- or a file that happens to share an
        id with an existing project -- never overwrites anything already
        in the library."""
        path, _ = QFileDialog.getOpenFileName(self, "Import Project", "", self.FILE_FILTER)
        if not path:
            return
        try:
            project = self._read_project_file(path)
        except ValueError as e:
            error_log.log_error("Import project file", e)
            self._toast_host.show_toast(str(e), kind="error", duration_ms=4500)
            return
        project.id = new_id()
        # Reassign every column/card id to fresh ones (rather than only
        # filling in blanks) so importing a file that was itself exported
        # from this same install never collides with the project it came
        # from. Card.column_id references are remapped alongside, since
        # cards identify their column by id, not by position.
        column_id_map = {}
        for column in project.columns:
            old_id = column.id
            column.id = new_id()
            column_id_map[old_id] = column.id
        for card in project.cards:
            card.id = new_id()
            card.column_id = column_id_map.get(card.column_id, card.column_id)
        remap_view_columns(project, column_id_map)
        existing_names = {p.name for p in self.storage.projects}
        if project.name in existing_names:
            base_name = project.name
            n = 2
            while f"{base_name} ({n})" in existing_names:
                n += 1
            project.name = f"{base_name} ({n})"
        self.storage.add_project(project)
        self._refresh_project_selector()
        self._load_active_project()
        self._toast_host.show_toast(f"Imported '{project.name}'", kind="success")

    @staticmethod
    def _description_to_plain(card: Card) -> str:
        """Plain-text rendering of a card's description for export,
        stripping rich-text HTML markup (bold/italic/underline/font tags)
        when present -- Markdown/plain-text export files are meant to be
        readable in any text editor, not rendered as HTML, so the raw
        markup would otherwise show up as literal "<span...>" noise in
        the exported file. QTextDocument is used purely as an HTML->text
        converter here (already a hard dependency via QTextEdit elsewhere
        in this app), not for any editing/rendering purpose."""
        if not card.description:
            return ""
        if not card.description_is_html:
            return card.description
        doc = QTextDocument()
        from safe_html import safe_rich_text
        doc.setHtml(safe_rich_text(card.description))
        return doc.toPlainText().strip()

    EXPORT_FILTER = "Markdown (*.md);;Text file (*.txt)"

    def _default_export_text_filename(self, project: Project, extension: str) -> str:
        safe = "".join(c if (c.isalnum() or c in " -_") else "_" for c in project.name).strip() or "project"
        return f"{safe}.{extension}"

    def _build_export_text(self, project: Project, as_markdown: bool) -> str:
        """Render every column and card in the project as readable text,
        grouped by column in their current display order and by card in
        their current position within each column -- the same order the
        board itself shows them in. as_markdown controls only the
        formatting (headings/bullets vs. a plain indented list); the
        content and structure are identical either way, so switching the
        file extension in the save dialog never changes what's included."""
        lines = [f"# {project.name}" if as_markdown else project.name]
        lines.append("")
        for column in sorted(project.columns, key=lambda c: c.order):
            lines.append(f"## {column.name}" if as_markdown else f"{column.name}")
            lines.append("" if as_markdown else "-" * len(column.name))
            column_cards = sorted(
                [c for c in project.cards if c.column_id == column.id],
                key=lambda c: c.order,
            )
            if not column_cards:
                lines.append("_No cards._" if as_markdown else "(No cards.)")
            for card in column_cards:
                type_tag = f"[{card.card_type}]"
                if as_markdown:
                    lines.append(f"- **{type_tag} {card.title}**")
                else:
                    lines.append(f"- {type_tag} {card.title}")
                if card.labels:
                    lines.append('    Labels: ' + ', '.join(card.labels))
                if card.due_at is not None:
                    lines.append('    Due: ' + due_text(card.due_at))
                if card.attachments:
                    lines.append('    Files: ' + ', '.join(a['name'] for a in card.attachments))
                desc = self._description_to_plain(card)
                if desc:
                    for desc_line in desc.splitlines():
                        lines.append(f"    {desc_line}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _on_export_file(self):
        """Export the active project as a human-readable Markdown or
        plain-text file (chosen via the save dialog's filter, same pattern
        as Save As's own filter list). This is a one-way, read-only
        export for sharing/printing/pasting elsewhere -- unlike Save As/
        Quick Save, an exported .md/.txt file is never itself something
        this app opens back up (it's not the structured .fboard.json
        format Open/Import expect), so there's no Quick-Export target to
        remember."""
        project = self.active_project
        if not project:
            return
        path, chosen_filter = QFileDialog.getSaveFileName(
            self, "Export Project", self._default_export_text_filename(project, "md"), self.EXPORT_FILTER
        )
        if not path:
            return
        as_markdown = "*.md" in chosen_filter
        # If the user typed an extension explicitly (or edited the
        # suggested filename), honor whichever extension is actually on
        # the path rather than the filter, so e.g. picking the Markdown
        # filter but typing "notes.txt" doesn't silently produce a
        # ".md"-formatted file with a ".txt" name.
        lower = path.lower()
        if lower.endswith(".txt"):
            as_markdown = False
        elif lower.endswith(".md"):
            as_markdown = True
        elif "." not in os.path.basename(path):
            path += ".md" if as_markdown else ".txt"
        text = self._build_export_text(project, as_markdown)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            error_log.log_error("Export project", e)
            self._toast_host.show_toast(
                f"Couldn't export the project: {e}", kind="error", duration_ms=4500,
            )
            return
        self._toast_host.show_toast(f"Exported '{project.name}'", kind="success")

    # ------------------------------------------------------------- settings
    def _diagnostics_payload(self) -> dict:
        project = self.active_project
        return {
            "version": app_meta.APP_VERSION,
            "file_size_bytes": self.storage.file_size_bytes(),
            "columns": len(project.columns) if project else 0,
            "cards": len(project.cards) if project else 0,
            "can_undo": self._board_clear_undo is not None,
        }

    def _on_open_settings(self):
        # A fresh Settings session starts with no pending undo: any clear
        # from a previous Settings visit is no longer reversible once the
        # dialog has been closed, since the person may have since edited
        # the board (added cards, switched projects) in ways that would
        # make "restoring" the old snapshot confusing/surprising rather
        # than a plain undo.
        self._board_clear_undo = None

        original_theme = self.storage.get_setting("theme", styles.DEFAULT_THEME)
        dialog = SettingsDialog(
            self,
            current_theme=original_theme,
            confirm_deletes=self.storage.get_setting("confirm_deletes", True),
            card_numbering=self.storage.get_setting("card_numbering", True),
            reduced_motion=self.storage.get_setting("reduced_motion", False),
            large_text=self.storage.get_setting("large_text", False),
            focus_outlines=self.storage.get_setting("focus_outlines", True),
            remember_last_project=self.storage.get_setting("remember_last_project", True),
            double_click_opens_card=self.storage.get_setting("double_click_opens_card", True),
            larger_click_targets=self.storage.get_setting("larger_click_targets", False),
            always_show_drop_zones=self.storage.get_setting("always_show_drop_zones", False),
            uppercase_card_text=self.storage.get_setting("uppercase_card_text", True),
            ui_scale=self.storage.get_setting("ui_scale", 100),
            diagnostics=self._diagnostics_payload(),
            ui_font=self.storage.get_setting("ui_font", "SF Pro Text"),
            reader_font_size=self.storage.get_setting("reader_font_size", 12),
        )
        # Apply/swatch clicks live-preview the theme immediately, without
        # closing the dialog or writing it to disk yet.
        dialog.themeApplied.connect(self._apply_theme)
        dialog.clearBoardRequested.connect(lambda: self._on_clear_board(dialog))
        dialog.revertBoardRequested.connect(lambda: self._on_revert_board(dialog))
        dialog.clearErrorLogRequested.connect(lambda: self._on_clear_error_log(dialog))
        dialog.manageCardTypesRequested.connect(self._on_open_manage_card_types)

        if dialog.exec():
            values = dialog.get_values()
            # Single batched write instead of six separate set_setting()
            # calls (each of which would otherwise rewrite the whole data
            # file, including every project/card, just to persist settings).
            numbering_changed = values["card_numbering"] != self.storage.get_setting("card_numbering", True)
            uppercase_changed = values["uppercase_card_text"] != self.storage.get_setting("uppercase_card_text", True)
            self.storage.update_settings({
                "theme": values["theme"],
                "ui_font": values["ui_font"],
                "reader_font_size": values["reader_font_size"],
                "confirm_deletes": values["confirm_deletes"],
                "card_numbering": values["card_numbering"],
                "large_text": values["large_text"],
                "ui_scale": values["ui_scale"],
                "reduced_motion": values["reduced_motion"],
                "focus_outlines": values["focus_outlines"],
                "remember_last_project": values["remember_last_project"],
                "double_click_opens_card": values["double_click_opens_card"],
                "uppercase_card_text": values["uppercase_card_text"],
                "larger_click_targets": values["larger_click_targets"],
                "always_show_drop_zones": values["always_show_drop_zones"],
            })
            self.scroll_area.set_reduced_motion(values["reduced_motion"])
            for cw in self._column_widgets.values():
                cw.set_reduced_motion(values["reduced_motion"])
                cw.set_always_highlight_drop_zone(values["always_show_drop_zones"])
            from card_widget import FeatureCardWidget
            FeatureCardWidget.double_click_opens_card = values["double_click_opens_card"]
            FeatureCardWidget.uppercase_card_text = values["uppercase_card_text"]
            self._apply_theme(values["theme"])
            # Only card numbering / the uppercase-text display setting
            # actually require re-rendering card widgets; theme/large-
            # text/ui-scale/focus-outlines are applied above via the
            # global stylesheet and reduced-motion is applied directly to
            # the existing scroll areas, so a full column teardown+rebuild
            # (_load_active_project) is unnecessary unless one of those
            # two changed.
            if numbering_changed or uppercase_changed:
                self._refresh_all_columns()
        else:
            # Cancelled: undo any live preview from Apply/swatch clicks and
            # restore the theme that was active when Settings was opened.
            self._apply_theme(original_theme)

    def _on_clear_board(self, dialog: SettingsDialog):
        """Diagnostics > Clear Board: remove every column and card in the
        current project (the project itself, its name, and other projects
        are untouched), after snapshotting them so Undo can restore
        exactly this state. Persists immediately -- like every other
        board mutation in this file -- rather than waiting for Settings'
        own OK, so a subsequent crash or force-quit can't lose the clear
        (or leave the on-disk file and the visible board disagreeing)."""
        project = self.active_project
        if not project:
            return
        self._board_clear_undo = (
            project.id,
            copy.deepcopy(project.columns),
            copy.deepcopy(project.cards),
        )
        project.columns = []
        project.cards = []
        self._save(project.id)
        self._load_active_project()
        dialog.refresh_diagnostics(self._diagnostics_payload())

    def _on_revert_board(self, dialog: SettingsDialog):
        """Diagnostics > Undo: restore exactly what the last Clear Board
        removed, provided the active project is still the one that was
        cleared (it can't have been deleted or switched away from in the
        meantime, since this dialog is modal and blocks the rest of the
        app while open -- this guard is a defensive no-op in practice,
        not a reachable path today)."""
        if self._board_clear_undo is None:
            return
        project_id, columns, cards = self._board_clear_undo
        project = self.storage.get_project(project_id)
        if project is None:
            self._board_clear_undo = None
            dialog.refresh_diagnostics(self._diagnostics_payload())
            return
        project.columns = copy.deepcopy(columns)
        project.cards = copy.deepcopy(cards)
        self._board_clear_undo = None
        self._save(project.id)
        self._load_active_project()
        dialog.refresh_diagnostics(self._diagnostics_payload())

    def _on_clear_error_log(self, dialog: SettingsDialog):
        """Diagnostics > Clear Log: clears error_log's in-memory buffer
        and truncates its on-disk file. Doesn't touch board data or
        _board_clear_undo -- entirely separate from Clear Board -- so it's
        safe to press regardless of any pending clear-board undo state."""
        error_log.clear()
        dialog.refresh_diagnostics(self._diagnostics_payload())

    def _confirm_deletes_enabled(self) -> bool:
        return self.storage.get_setting("confirm_deletes", True)

    def _custom_card_types(self):
        """Types that need a palette-cycled color/icon rather than one of
        the fixed built-in colors -- true custom types plus any built-in
        that's been renamed (see storage.Storage.palette_card_types).
        This is what gets passed as `custom_types` to card_type_color/
        card_type_icon and every CardWidget/ColumnWidget, so a renamed
        built-in keeps a stable, distinct color/icon exactly like a
        custom type does."""
        return self.storage.palette_card_types()

    def _available_card_types(self):
        """Every card type currently offered by the type pickers -- see
        storage.Storage.available_card_types for the built-in-rename/
        delete-aware ordering this now applies (previously just
        CARD_TYPES + custom types, since built-ins couldn't be renamed
        or deleted)."""
        return self.storage.available_card_types()

    def _default_card_type(self) -> str:
        """The type new cards get when none is explicitly chosen (inline
        quick-add). Used to be a hardcoded CARD_TYPES[0] ("Add"), but that
        type can now be renamed or deleted (see the type-management
        changes above) -- this falls back to the first *currently
        available* type instead, so quick-add never assigns a type that
        no longer exists in the picker."""
        available = self._available_card_types()
        return available[0] if available else ""

    def _card_type_usage_counts(self):
        """How many cards currently use each card type -- built-in or
        custom -- counted across every loaded project (not just the
        active one), since a type can be in use on cards in a project
        that isn't currently open. Purely informational, shown in
        ManageCardTypesDialog next to each type so deleting a
        heavily-used one isn't a surprise."""
        counts = {}
        for project in self.storage.projects:
            for card in project.cards:
                counts[card.card_type] = counts.get(card.card_type, 0) + 1
        return counts

    def _on_manage_type_rename(self, old_name: str, new_name: str):
        """Relayed from CardDialog.manageTypesRenameRequested (see
        dialogs.ManageCardTypesDialog) -- performs the actual rename
        across every project's cards and persists it. A full board reload
        follows since the rename can affect cards in any column of the
        currently open project (not just whichever column the CardDialog
        that triggered this happened to be opened from)."""
        if self.storage.rename_card_type(old_name, new_name):
            self._load_active_project()

    def _on_manage_type_delete(self, name: str):
        """Relayed from CardDialog.manageTypesDeleteRequested. Cards using
        the deleted type are reassigned to the next remaining type by
        Storage.delete_card_type itself; this just triggers the board
        reload afterward, same reasoning as _on_manage_type_rename
        above."""
        self.storage.delete_card_type(name)
        self._load_active_project()

    def _on_open_manage_card_types(self):
        """Settings > General > "Manage..." button (see SettingsDialog's
        manageCardTypesRequested) -- opens the same ManageCardTypesDialog
        CardDialog's own "Manage Types..." entry uses, but reachable
        directly without first having to open a card. Settings itself
        stays open underneath (it's the caller, via
        dialog.manageCardTypesRequested.connect in _on_open_settings) so
        pressing "Manage..." again after closing this reopens it fresh
        against whatever the list looks like now."""
        dialog = ManageCardTypesDialog(
            self, all_types=self._available_card_types(),
            usage_counts=self._card_type_usage_counts(),
        )
        dialog.renameRequested.connect(
            lambda old, new: self._on_manage_type_rename_and_refresh(dialog, old, new)
        )
        dialog.deleteRequested.connect(
            lambda name: self._on_manage_type_delete_and_refresh(dialog, name)
        )
        dialog.exec()

    def _on_manage_type_rename_and_refresh(self, dialog, old_name: str, new_name: str):
        self._on_manage_type_rename(old_name, new_name)
        dialog.refresh_types(self._available_card_types(), self._card_type_usage_counts())

    def _on_manage_type_delete_and_refresh(self, dialog, name: str):
        self._on_manage_type_delete(name)
        dialog.refresh_types(self._available_card_types(), self._card_type_usage_counts())

    # -------------------------------------------------------------- board
    def _load_active_project(self):
        project = self.active_project
        self.workspace.set_project(project)
        # Clear existing column widgets
        for cw in list(self._column_widgets.values()):
            self.board_layout.removeWidget(cw)
            cw.setParent(None)
            cw.deleteLater()
        self._column_widgets.clear()
        # A full reload tears down and rebuilds every ColumnWidget/card
        # widget from scratch (project switch, column add/remove/reorder,
        # Clear Board, undo/redo, etc.), so any prior multi-selection
        # would otherwise silently keep referencing card ids that may no
        # longer exist, or may now belong to a different project. Session/
        # UI-only state, like the per-column type filter -- reset here for
        # the same reason that's reset on rebuild.
        self._selected_card_ids.clear()
        self._selection_anchor = None

        if project is None:
            self._update_window_width()
            return

        # remove trailing stretch, we'll re-add
        for i in reversed(range(self.board_layout.count())):
            item = self.board_layout.itemAt(i)
            if item.spacerItem():
                self.board_layout.removeItem(item)

        custom_types = self._custom_card_types()
        reduced_motion = self.storage.get_setting("reduced_motion", False)
        project_sort_state = self._column_sort_state.setdefault(project.id, {})
        for accent_index, column in enumerate(sorted(project.columns, key=lambda c: c.order)):
            # Prefer the column's own persisted sort (survives closing and
            # reopening the app); fall back to this session's in-memory
            # record (covers a rebuild triggered without a fresh project
            # load, e.g. after add/remove/reorder) and finally to the
            # column's own field again as the ultimate default.
            saved_key, saved_desc = project_sort_state.get(
                column.id, (column.sort_key, column.sort_descending)
            )
            cw = ColumnWidget(
                column, custom_types=custom_types, reduced_motion=reduced_motion,
                accent_index=accent_index,
                initial_sort_key=saved_key, initial_sort_descending=saved_desc,
            )
            if column.width is not None:
                cw.set_column_width(column.width)
            cw.set_always_highlight_drop_zone(self.storage.get_setting("always_show_drop_zones", False))
            cw.sortStateChanged.connect(self._on_column_sort_state_changed)
            cw.widthChanged.connect(self._on_column_width_changed)
            cw.cardDropped.connect(self._on_card_dropped)
            cw.addCardRequested.connect(self._on_add_card)
            cw.quickAddRequested.connect(self._on_quick_add_card)
            cw.cardEditRequested.connect(self._on_edit_card)
            cw.cardDeleteRequested.connect(self._on_delete_card)
            cw.cardDuplicateRequested.connect(self._on_duplicate_card)
            cw.cardSelectRequested.connect(self._on_card_select_requested)
            cw.cardCheckToggled.connect(self._on_card_check_toggled)
            cw.cardTypeChangeRequested.connect(self._on_card_type_changed)
            cw.cardPriorityChangeRequested.connect(self._on_card_priority_changed)
            cw.cardGroupDropped.connect(self._on_card_group_dropped)
            cw.renameRequested.connect(self._on_rename_column)
            cw.deleteRequested.connect(self._on_delete_column)
            cw.moveLeftRequested.connect(self._on_move_column_left)
            cw.moveRightRequested.connect(self._on_move_column_right)
            cw.columnDropped.connect(self._on_column_dropped)
            self.board_layout.addWidget(cw)
            self._column_widgets[column.id] = cw

        self.board_layout.addStretch()
        self._refresh_all_columns()
        self._update_window_width()

    def _on_column_sort_state_changed(self, column_id: str, sort_key, descending: bool):
        """Persist a column's "Sort by" choice for the active project (see
        _column_sort_state / ColumnWidget.sortStateChanged), so switching
        away to another project and back restores this exact sort mode/
        direction instead of resetting to "Board order". Also written onto
        the Column model itself and saved to disk (see Column.sort_key/
        sort_descending) so the same restore now also survives closing and
        reopening the app entirely, not just switching projects within one
        session -- while still never touching card.order or drag/drop,
        matching the existing display-only sort contract."""
        project = self.active_project
        if project is None:
            return
        self._column_sort_state.setdefault(project.id, {})[column_id] = (sort_key, descending)
        for column in project.columns:
            if column.id == column_id:
                if column.sort_key == sort_key and column.sort_descending == descending:
                    return  # no actual change -- skip an unnecessary save
                column.sort_key = sort_key
                column.sort_descending = descending
                self._save(project.id)
                break

    def _refresh_all_columns(self):
        project = self.active_project
        if project is None:
            return
        self._refresh_columns(c.id for c in project.columns)

    def _refresh_columns(self, column_ids):
        """Re-render only the given columns' card lists, instead of tearing
        down and recreating every FeatureCardWidget in every column on the
        board for a change that only ever affects one or two columns (an
        add/edit/delete touches one column; a drag-drop touches at most
        two: the source and the target)."""
        project = self.active_project
        if project is None:
            return
        show_numbers = self.storage.get_setting("card_numbering", True)
        # Keep each ColumnWidget's custom-type list current: a new custom
        # type can be created from the Add/Edit Card dialog in the same
        # action that triggers this partial refresh, so the widget's
        # cached copy (set once at column-build time) would otherwise be
        # stale until the next full board reload.
        custom_types = self._custom_card_types()
        all_card_ids = {c.id for c in project.cards}
        # Prune any selected card ids that no longer exist in this project
        # (deleted, or the project itself changed underneath a partial
        # refresh) so a stale id never lingers in the selection set for a
        # bulk action to later trip over.
        self._selected_card_ids &= all_card_ids
        for column_id in set(column_ids):
            cw = self._column_widgets.get(column_id)
            if cw is None:
                continue
            cw.update_custom_types(custom_types)
            cw.set_selected_ids(self._selected_card_ids)
            cards = sorted(
                [c for c in project.cards if c.column_id == column_id and self.workspace.matches(c)],
                key=lambda c: c.order
            )
            cw.set_cards(cards, show_numbers=show_numbers)
        self._update_selection_bar()
        self.workspace.refresh()

    # -------------------------------------------------------- window sizing
    def _ideal_window_width(self) -> int:
        """Width that exactly fits the visible columns (or one card's worth
        of space if the board is empty), so there's no dead space on the
        right and the window grows/shrinks as columns are added/removed."""
        project = self.active_project
        num_columns = len(project.columns) if project else 0

        if num_columns == 0:
            # Reserve only enough width for a single card + margins, per
            # the "minimise deadspace when empty" requirement.
            content_width = 220 + 20  # card width + its own inner margins
        else:
            content_width = (num_columns * COLUMN_WIDTH) + ((num_columns - 1) * BOARD_SPACING)

        # No "+24" breathing-room fudge here: the vertical scrollbar is
        # permanently off (setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # above) so it never needs reserved width, and the scroll area now
        # has no frame (see _build_ui) so there's no frame width to
        # account for either. BOARD_MARGIN already reserves the board
        # layout's own left/right content margins, which is the actual
        # source of breathing room around the last column -- adding a
        # second, unrelated flat padding on top of that produced literal
        # dead space (an empty gutter the width of nothing in particular)
        # on the right of the window, which is what this was cutting.
        width = content_width + (BOARD_MARGIN * 2)

        screen = QApplication.primaryScreen()
        if screen is not None:
            max_width = int(screen.availableGeometry().width() * MAX_WINDOW_WIDTH_FRACTION)
            width = min(width, max_width)

        return max(width, 420)  # never smaller than a single-card minimum

    def _update_window_width(self):
        """Resize the window to hug its content -- but only when that's
        still expected: on first load, or when the number of columns has
        actually changed since the last time this ran. Once the person has
        manually resized the window horizontally, a reload that doesn't
        change the column count (switching projects, reordering columns,
        opening a file with the same column count, a Settings change,
        etc.) leaves their chosen width alone instead of silently
        snapping it back to the content-fit width. Height is left as-is
        either way (user may have resized vertically)."""
        project = self.active_project
        num_columns = len(project.columns) if project else 0
        column_count_changed = num_columns != getattr(self, "_last_fitted_column_count", None)

        if self._user_resized_width and not column_count_changed:
            # The window itself keeps its user-chosen width, but the
            # ColumnWidgets that _load_active_project() just tore down and
            # rebuilt are brand new objects at their default (comfortable)
            # width -- they don't inherit the evenly-stretched/shrunk width
            # the previous set had. Without re-running the stretch pass
            # here, a project switch (or column reorder/reload) at the
            # same column count would leave the freshly built columns at
            # their default width, showing dead space to the right of the
            # last column until the next manual resize nudged
            # _apply_column_stretch_width to run again. Re-fit them to the
            # window's current (unchanged) width immediately instead, same
            # deferred-one-event-loop-turn reasoning as the resize path
            # below.
            self._last_fitted_column_count = num_columns
            QTimer.singleShot(0, self._apply_column_stretch_width)
            QTimer.singleShot(0, self._apply_topbar_scale)
            return

        target_width = self._ideal_window_width()
        current_height = max(self.height(), MIN_WINDOW_HEIGHT)
        if not self.isMaximized() and not self.isFullScreen():
            self._resize_programmatically(target_width, current_height)
        self._last_fitted_column_count = num_columns
        # Deferred one event-loop turn (same reasoning as showEvent's
        # QTimer.singleShot(0, ...) above _apply_initial_size): the
        # resize() call just above is synchronous on the window itself,
        # but the scroll area's viewport doesn't have its final laid-out
        # width until the pending layout pass actually runs, so reading
        # viewport().width() here immediately would see a stale size.
        QTimer.singleShot(0, self._apply_column_stretch_width)
        QTimer.singleShot(0, self._apply_topbar_scale)

    def _apply_column_stretch_width(self):
        """Fit every visible column to the window's actual width instead of
        letting any column go off-screen behind a horizontal scrollbar:
        - Wider than the columns' combined comfortable width (COLUMN_WIDTH
          each): grow every column evenly to fill the extra space, up to
          COLUMN_MAX_WIDTH, e.g. maximizing the window makes the columns
          themselves bigger instead of just revealing blank canvas.
        - Narrower than that: shrink every column evenly instead, down to
          COLUMN_MIN_WIDTH, so all columns stay visible (each one simply
          renders narrower, with its cards shrunk to match -- see
          ColumnWidget.set_column_width) rather than some being scrolled
          out of view.
        - Narrower than COLUMN_MIN_WIDTH per column even at that floor: the
          board falls back to horizontal scrolling (columns held at
          COLUMN_MIN_WIDTH) rather than shrinking further, since below that
          width cards/labels are no longer legible.

        This adjusts each ColumnWidget's fixed width directly rather than
        switching their size policy to Expanding: an HBoxLayout of
        Expanding widgets would divide space using Qt's stretch-factor
        rules (which default to giving all extra space to the *last*
        widget added, not splitting it evenly) and would also reopen the
        fixed-width assumptions the drag/drop indicator math in
        ColumnWidget relies on for a plain, predictable per-column width.
        """
        if not self._column_widgets:
            return
        # Guard against the debounce timer firing before _build_ui() has
        # created scroll_area (possible since Qt can deliver a resizeEvent
        # during widget construction/activation, before this window is
        # ever shown -- see the isVisible() guard already used for the
        # same reason elsewhere in this class).
        scroll_area = getattr(self, "scroll_area", None)
        if scroll_area is None:
            return
        columns = list(self._column_widgets.values())
        n = len(columns)

        viewport_width = scroll_area.viewport().width()
        available = viewport_width - (BOARD_MARGIN * 2) - (BOARD_SPACING * (n - 1))
        fixed = {cw.column.id: cw.column.width for cw in columns if cw.column.width is not None}
        auto_count = n - len(fixed)
        remaining = available - sum(fixed.values())
        target = max(COLUMN_MIN_WIDTH, min(COLUMN_MAX_WIDTH, remaining // auto_count)) if auto_count else COLUMN_WIDTH
        for cw in columns:
            cw.set_column_width(fixed.get(cw.column.id, target))

    def _apply_topbar_scale(self):
        """Shrinks or grows every top-bar control's font together as the
        window is resized, so the whole row keeps fitting inside the
        window's actual width instead of relying on the scroll area to
        hide the overflow. Mirrors _apply_column_stretch_width's
        shrink/grow-evenly approach: one scale factor applied to every
        control (not per-widget truncation), so the toolbar keeps a
        consistent, legible look at any width rather than some buttons
        shrinking more than others. The scroll area above stays as a
        fallback for the (rare) case where even the smallest allowed scale
        still doesn't fit -- it never needs to activate for any width this
        loop can actually reach down to.
        """
        top_bar = getattr(self, "_top_bar_widget", None)
        top_bar_scroll = getattr(self, "_top_bar_scroll", None)
        base_sizes = getattr(self, "_topbar_base_point_sizes", None)
        if not top_bar or not top_bar_scroll or not base_sizes:
            return

        layout = top_bar.layout()
        if layout is None:
            return

        # Natural (100%-scale) width of the row's content, computed from
        # each widget's current sizeHint at whatever scale is already
        # applied, backed out to what it'd be at 100% by dividing through
        # the currently-applied factor -- avoids having to rebuild the row
        # at 1.0 scale just to measure it.
        current_factor = self._topbar_scale_factor or 1.0
        content_width_at_current = layout.sizeHint().width()
        natural_width = content_width_at_current / current_factor if current_factor else content_width_at_current

        available = top_bar_scroll.viewport().width()
        if natural_width <= 0 or available <= 0:
            return

        MIN_SCALE, MAX_SCALE = 0.72, 1.0
        factor = available / natural_width
        factor = max(MIN_SCALE, min(MAX_SCALE, factor))

        if abs(factor - current_factor) < 0.01:
            return
        self._topbar_scale_factor = factor

        for w, base_px in base_sizes.items():
            scaled_px = max(9, round(base_px * factor))
            # Inline per-widget stylesheet (not setFont()): the app-level
            # stylesheet sets font-size on QWidget/#AppTitle/#IconButton
            # by selector, which otherwise always wins over a plain QFont
            # point-size change. Only font-size is touched here, so every
            # other property (color, padding, hover states, etc.) still
            # comes from the real theme stylesheet as normal.
            w.setStyleSheet(f"font-size: {scaled_px}px;")

        # #ProjectSelector's own QSS rule sets "min-width: 170px", which --
        # same as font-size above -- always wins over setMinimumWidth() in
        # code, so the shrink has to go through an inline stylesheet here
        # too rather than the plain Qt property. Font-size reuses this
        # widget's own captured base size (same base_sizes dict as the
        # generic loop above) instead of a separate hardcoded 13 -- that
        # hardcoded value didn't track "Larger text" (base 15px) the same
        # way the hardcoded #IconButton 18 above didn't, so this had the
        # same latent bug: narrowing the window while large_text was on
        # would snap the project selector's text back to normal size.
        base_min_w = getattr(self, "_topbar_project_selector_base_min_width", 170) or 170
        scaled_min_w = max(90, round(base_min_w * factor))
        selector_base_px = base_sizes.get(self.project_selector, 14)
        scaled_px = max(9, round(selector_base_px * factor))
        self.project_selector.setStyleSheet(f"font-size: {scaled_px}px; min-width: {scaled_min_w}px;")

        # #IconButton's own QSS rule likewise sets min-width/min-height
        # (34px) directly, so the gear button's shrink goes through the
        # same inline-stylesheet override as everything else above. The
        # font-size portion reuses this same button's own captured base
        # size (from base_sizes, set in _topbar_capture_base_sizes) rather
        # than a separate hardcoded 18 here -- that hardcoded value didn't
        # track "Larger text" being on (which raises the base to 20px),
        # so narrowing the window while large_text was on used to snap the
        # gear glyph back down to the normal-text size instead of scaling
        # from the actual (larger) baseline like every other control here.
        for btn in getattr(self, "_topbar_icon_buttons", []):
            base_dim = getattr(self, "_topbar_icon_button_base_dim", 28)
            dim = max(24, round(base_dim * factor))
            icon_base_px = base_sizes.get(btn, 19)
            btn.setStyleSheet(
                f"font-size: {max(9, round(icon_base_px * factor))}px; "
                f"min-width: {dim}px; min-height: {dim}px;"
            )

    # --------------------------------------------------------- card actions
    def _on_new_card_default(self):
        project = self.active_project
        if not project or not project.columns:
            return
        first_col = sorted(project.columns, key=lambda c: c.order)[0]
        self._on_add_card(first_col.id)

    def _on_add_card(self, column_id: str):
        dialog = CardDialog(
            self, heading="\u2795 Add Card", available_types=self._available_card_types(),
            type_usage_counts=self._card_type_usage_counts(),
            attachment_store=self.storage.attachments, attachment_budget=self._attachment_budget(),
            attachment_hashes={a["sha256"] for c in self.active_project.cards for a in c.attachments},
        )
        dialog.manageTypesRenameRequested.connect(self._on_manage_type_rename)
        dialog.manageTypesDeleteRequested.connect(self._on_manage_type_delete)
        if dialog.exec():
            values = dialog.get_values()
            if values.get("new_card_type"):
                # defer_save=True: the card append below performs the save
                # for this whole action, avoiding a redundant disk write.
                self.storage.add_custom_card_type(values["new_card_type"], defer_save=True)
            project = self.active_project
            before = self._snapshot_project_state(project)
            existing = [c for c in project.cards if c.column_id == column_id]
            max_order = max([c.order for c in existing], default=-1)
            card = Card(
                id=new_id(),
                title=values["title"],
                description=values["description"],
                description_is_html=values["description_is_html"],
                card_type=values["card_type"],
                priority=values.get("priority", ""),
                column_id=column_id,
                order=max_order + 1,
            )
            apply_card_details(card, values)
            project.cards.append(card)
            self._save(project.id)
            self._record_undo_step(project, before)
            self._refresh_columns([column_id])

    def _on_quick_add_card(self, column_id: str, title: str):
        """Inline quick-add: append a card with just a title (default
        type, no description) directly to the given column, without
        opening CardDialog. Mirrors _on_add_card's own ordering/save/
        refresh logic exactly, just with fixed type/description instead
        of values from a dialog -- the card is a completely normal card
        afterward (editable, draggable, etc.), this only skips the dialog
        for the initial creation."""
        project = self.active_project
        if not project:
            return
        before = self._snapshot_project_state(project)
        existing = [c for c in project.cards if c.column_id == column_id]
        max_order = max([c.order for c in existing], default=-1)
        card = Card(
            id=new_id(),
            title=title,
            description="",
            description_is_html=False,
            card_type=self._default_card_type(),
            column_id=column_id,
            order=max_order + 1,
        )
        project.cards.append(card)
        self._save(project.id)
        self._record_undo_step(project, before)
        self._refresh_columns([column_id])

    def _on_edit_card(self, card_id: str):
        project = self.active_project
        card = next((c for c in project.cards if c.id == card_id), None)
        if not card:
            return
        dialog = CardDialog(
            self, title=card.title, description=card.description,
            description_is_html=card.description_is_html,
            card_type=card.card_type, priority=card.priority, heading="\u270F\uFE0F Edit Card",
            available_types=self._available_card_types(),
            type_usage_counts=self._card_type_usage_counts(),
            labels=card.labels, due_at=card.due_at, reminder_at=card.reminder_at, attachments=card.attachments,
            attachment_store=self.storage.attachments, attachment_budget=self._attachment_budget(card.id),
            attachment_hashes={a["sha256"] for c in project.cards if c.id != card.id for a in c.attachments},
        )
        dialog.manageTypesRenameRequested.connect(self._on_manage_type_rename)
        dialog.manageTypesDeleteRequested.connect(self._on_manage_type_delete)
        if dialog.exec():
            values = dialog.get_values()
            before = self._snapshot_project_state(project)
            if values.get("new_card_type"):
                # defer_save=True: card.updated_at + storage.save() below
                # covers persisting this whole action in a single write.
                self.storage.add_custom_card_type(values["new_card_type"], defer_save=True)
            card.title = values["title"]
            card.description = values["description"]
            card.description_is_html = values["description_is_html"]
            card.card_type = values["card_type"]
            card.priority = values.get("priority", "")
            apply_card_details(card, values)
            card.updated_at = time.time()
            self._save(project.id)
            self._record_undo_step(project, before)
            self._refresh_columns([card.column_id])

    def _on_delete_card(self, card_id: str):
        project = self.active_project
        card = next((c for c in project.cards if c.id == card_id), None)
        if not card:
            return
        if self._confirm_deletes_enabled():
            confirm = QMessageBox.question(
                self, "\U0001F5D1\uFE0F Delete Card",
                f"Delete card '{card.title}'?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return
        before = self._snapshot_project_state(project)
        # Also drop the card from any active multi-selection, so a
        # subsequent bulk action never references a card that no longer
        # exists.
        self._selected_card_ids.discard(card_id)
        project.cards = [c for c in project.cards if c.id != card_id]
        self._save(project.id)
        self._record_undo_step(project, before)
        self._refresh_columns([card.column_id])

    def _on_duplicate_card(self, card_id: str):
        """Card Options > Duplicate: insert a copy of the card directly
        after the original in the same column, with a fresh id (so it's a
        wholly independent card, not an alias) and its own timestamps."""
        project = self.active_project
        if not project:
            return
        card = next((c for c in project.cards if c.id == card_id), None)
        if not card:
            return
        before = self._snapshot_project_state(project)
        now = time.time()
        new_card = copy.deepcopy(card)
        new_card.id = new_id()
        new_card.created_at = now
        new_card.updated_at = now
        # Shift every card at or after the original's order up by one, so
        # the duplicate lands immediately after it instead of at the end
        # of the column.
        for c in project.cards:
            if c.column_id == card.column_id and c.order > card.order:
                c.order += 1
        new_card.order = card.order + 1
        project.cards.append(new_card)
        self._save(project.id)
        self._record_undo_step(project, before)
        self._refresh_columns([card.column_id])

    def _on_card_type_changed(self, card_id: str, new_type: str):
        """Card's type badge quick-menu (see card_widget.FeatureCardWidget
        ._build_type_menu) picked a new type -- a faster path to retype a
        single card than opening the full Edit Card dialog. A no-op if
        the type didn't actually change (re-picking the current type),
        so it doesn't rewrite the data file or push an undo step for
        nothing."""
        project = self.active_project
        if not project or not new_type:
            return
        card = next((c for c in project.cards if c.id == card_id), None)
        if not card or card.card_type == new_type:
            return
        before = self._snapshot_project_state(project)
        card.card_type = new_type
        card.updated_at = time.time()
        self._save(project.id)
        self._record_undo_step(project, before)
        self._refresh_columns([card.column_id])

    def _on_card_priority_changed(self, card_id: str, new_priority: str):
        """Card's priority badge quick-menu (see card_widget
        .FeatureCardWidget._build_priority_menu) picked a new priority
        (or "None" to clear it, new_priority=""). Mirrors
        _on_card_type_changed's own no-op-if-unchanged guard."""
        project = self.active_project
        if not project:
            return
        card = next((c for c in project.cards if c.id == card_id), None)
        if not card or card.priority == new_priority:
            return
        before = self._snapshot_project_state(project)
        card.priority = new_priority
        card.updated_at = time.time()
        self._save(project.id)
        self._record_undo_step(project, before)
        self._refresh_columns([card.column_id])

    def _on_card_dropped(self, card_id: str, target_column_id: str, index: int):
        project = self.active_project
        card = next((c for c in project.cards if c.id == card_id), None)
        if not card:
            return

        before = self._snapshot_project_state(project)
        source_column_id = card.column_id

        # Build ordered list of cards in the target column excluding the moving card
        target_cards = sorted(
            [c for c in project.cards if c.column_id == target_column_id and c.id != card_id],
            key=lambda c: c.order
        )
        index = max(0, min(index, len(target_cards)))
        target_cards.insert(index, card)

        # Detect a true no-op drop (card released back into the exact
        # column/position it started from, e.g. a drag that was started
        # then reconsidered) before mutating anything, so it doesn't
        # trigger a full data-file rewrite or column re-render for a
        # change that isn't actually a change -- consistent with the
        # no-op skip already applied to settings/rename/delete.
        changed = card.column_id != target_column_id
        if not changed:
            for i, c in enumerate(target_cards):
                if c.order != i:
                    changed = True
                    break
        if not changed:
            return

        moved_columns = card.column_id != target_column_id
        card.column_id = target_column_id
        card.updated_at = time.time()

        for i, c in enumerate(target_cards):
            c.order = i

        self._save(project.id)
        self._record_undo_step(project, before)
        # Unselect the card once it's actually moved to a different column
        # (a same-column reorder leaves the selection alone) so it doesn't
        # keep rendering as selected -- and the bulk-action bar keep
        # showing it -- in a column the person just dragged it out of/into.
        if moved_columns and card_id in self._selected_card_ids:
            self._selected_card_ids.discard(card_id)
            self._selection_anchor = None
            self._apply_selection_to_columns()
        self._refresh_columns([source_column_id, target_column_id])

    def _on_card_group_dropped(self, card_ids: list, target_column_id: str, index: int):
        """Shift/multi-select group drag-drop: move every selected card
        that's part of the drag together, landing at the same drop index
        as a single-card drop would, in the same relative order the
        group already had (by source column, then order) -- mirrors
        _bulk_move_selected's own ordering choice, but inserts at the
        dropped position instead of always appending to the end, since a
        drag-drop (unlike the bulk-action bar's "Move to...") has an
        explicit target position the person dragged to."""
        project = self.active_project
        if project is None:
            return
        cards = [c for c in project.cards if c.id in card_ids]
        if not cards:
            return
        before = self._snapshot_project_state(project)
        source_column_ids = {c.column_id for c in cards}
        moving_ids = {c.id for c in cards}

        # Cards already in the target column that are NOT part of this
        # drag, in their existing order -- the group is inserted into
        # this list at `index`, same semantics as the single-card path
        # in _on_card_dropped above (index is computed by ColumnWidget
        # against the target column's cards with the dragged card(s)
        # excluded).
        target_cards = sorted(
            [c for c in project.cards if c.column_id == target_column_id and c.id not in moving_ids],
            key=lambda c: c.order,
        )
        index = max(0, min(index, len(target_cards)))
        # Insert the whole moving group at once, preserving the group's
        # own relative order (source column, then order) rather than
        # whatever order card_ids happened to arrive in off the wire.
        group_sorted = sorted(cards, key=lambda c: (c.column_id, c.order))
        for offset, c in enumerate(group_sorted):
            target_cards.insert(index + offset, c)

        now = time.time()
        for c in group_sorted:
            c.column_id = target_column_id
            c.updated_at = now
        for i, c in enumerate(target_cards):
            c.order = i

        self._save(project.id)
        self._record_undo_step(project, before)
        # Unselect the moved cards immediately, same as the single-card
        # drop path above, instead of leaving them (and the bulk-action
        # bar) selected in their new column.
        if moving_ids & self._selected_card_ids:
            self._selected_card_ids -= moving_ids
            self._selection_anchor = None
            self._apply_selection_to_columns()
        self._refresh_columns(source_column_ids | {target_column_id})
        self._toast_host.show_toast(
            f"Moved {len(cards)} cards to the drop position", kind="success", duration_ms=1600,
        )

    # ------------------------------------------------------------- columns
    def _on_add_column(self):
        project = self.active_project
        if not project:
            return
        dialog = TextPromptDialog(self, heading="\u2795 Add Column", label="Column name", initial="")
        if dialog.exec():
            name = dialog.get_value()
            before = self._snapshot_project_state(project)
            max_order = max([c.order for c in project.columns], default=-1)
            col = Column(id=new_id(), name=name, order=max_order + 1)
            project.columns.append(col)
            self._save(project.id)
            self._record_undo_step(project, before)
            self._load_active_project()

    def _on_rename_column(self, column_id: str):
        project = self.active_project
        column = next((c for c in project.columns if c.id == column_id), None)
        if not column:
            return
        dialog = TextPromptDialog(self, heading="\u270F\uFE0F Rename Column", label="Column name", initial=column.name)
        if dialog.exec():
            new_name = dialog.get_value()
            before = self._snapshot_project_state(project)
            column.name = new_name
            self._save(project.id)
            self._record_undo_step(project, before)
            cw = self._column_widgets.get(column_id)
            if cw:
                cw.update_name(new_name)

    def _on_delete_column(self, column_id: str):
        project = self.active_project
        if not project:
            return
        column = next((c for c in project.columns if c.id == column_id), None)
        if not column:
            return
        card_count = len([c for c in project.cards if c.column_id == column_id])
        if self._confirm_deletes_enabled():
            if card_count:
                msg = (f"Delete column '{column.name}' and its {card_count} card"
                       f"{'s' if card_count != 1 else ''}?\nThis can't be undone.")
            else:
                msg = f"Delete column '{column.name}'?"
            confirm = QMessageBox.question(
                self, "\U0001F5D1\uFE0F Delete Column", msg,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return
        before = self._snapshot_project_state(project)
        # Drop any selected cards that lived in the deleted column, so a
        # subsequent bulk action never references a card that no longer
        # exists.
        removed_ids = {c.id for c in project.cards if c.column_id == column_id}
        self._selected_card_ids -= removed_ids
        self._column_sort_state.get(project.id, {}).pop(column_id, None)
        project.columns = [c for c in project.columns if c.id != column_id]
        project.cards = [c for c in project.cards if c.column_id != column_id]
        for i, c in enumerate(sorted(project.columns, key=lambda c: c.order)):
            c.order = i
        self._save(project.id)
        self._record_undo_step(project, before)
        self._load_active_project()

    def _swap_column_order(self, column_id: str, direction: int):
        """direction: -1 to move left/up in order, +1 to move right/down."""
        project = self.active_project
        if not project:
            return
        ordered = sorted(project.columns, key=lambda c: c.order)
        idx = next((i for i, c in enumerate(ordered) if c.id == column_id), None)
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(ordered):
            return
        before = self._snapshot_project_state(project)
        ordered[idx], ordered[new_idx] = ordered[new_idx], ordered[idx]
        for i, c in enumerate(ordered):
            c.order = i
        self._save(project.id)
        self._record_undo_step(project, before)
        self._load_active_project()

    def _on_move_column_left(self, column_id: str):
        self._swap_column_order(column_id, -1)

    def _on_move_column_right(self, column_id: str):
        self._swap_column_order(column_id, 1)

    def _on_column_dropped(self, dragged_column_id: str, target_column_id: str, insert_before: bool):
        """Reorder columns via drag & drop (mirrors the left/right-button
        reordering, but lets a column be dropped at any position directly)."""
        project = self.active_project
        if not project or dragged_column_id == target_column_id:
            return
        ordered = sorted(project.columns, key=lambda c: c.order)
        dragged = next((c for c in ordered if c.id == dragged_column_id), None)
        if dragged is None:
            return
        ordered.remove(dragged)
        target_idx = next((i for i, c in enumerate(ordered) if c.id == target_column_id), None)
        if target_idx is None:
            insert_idx = len(ordered)
        else:
            insert_idx = target_idx if insert_before else target_idx + 1
        ordered.insert(insert_idx, dragged)
        before = self._snapshot_project_state(project)
        for i, c in enumerate(ordered):
            c.order = i
        self._save(project.id)
        self._record_undo_step(project, before)
        self._load_active_project()
