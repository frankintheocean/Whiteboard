"""🧱 Show one status column and its cards."""
from smooth_scroll import SmoothVScrollArea
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy, QMenu,
    QToolButton, QScrollArea, QComboBox, QLineEdit
)
from PySide6.QtCore import QTimer, Qt, Signal, QMimeData, QPoint
from PySide6.QtGui import QDrag

from card_widget import FeatureCardWidget, CARD_MIME_TYPE, CARD_GROUP_MIME_TYPE
from models import Column, column_accent_color, CARD_TYPES, PRIORITY_LEVELS
import styles

# Sort options for each column's own "Sort by" combo box (view-only, same
# rendering-time-only contract as the type filter below: never touches
# card.order, project.cards, or what's saved to disk -- only the order
# cards are *displayed* in this column). "Board order" is the default and
# restores the normal drag/drop-defined order (i.e. no sort applied).
# Each entry is (item_text, sort_key_id); ascending/descending is a
# separate toggle (see _sort_dir_btn) rather than doubling the number of
# combo entries.
SORT_BOARD_ORDER = None
SORT_BY_TYPE = "type"
SORT_BY_PRIORITY = "priority"

# Priority rank used for sorting only (lower rank = higher/more-urgent
# priority, matching PRIORITY_LEVELS' own P0..P3 ordering); a card with no
# priority set ("") sorts after every explicit priority level in ascending
# order, same as it visually reads as "least urgent".
_PRIORITY_RANK = {level: i for i, level in enumerate(PRIORITY_LEVELS)}


def _priority_rank_for_card(priority: str) -> int:
    if priority in _PRIORITY_RANK:
        return _PRIORITY_RANK[priority]
    return len(PRIORITY_LEVELS)  # "no priority" sorts last in ascending order


def _type_sort_key(card_type: str, custom_types) -> tuple:
    """Stable sort key for card type: built-in CARD_TYPES first in their
    declared order, then this column's known custom types in the order
    they were added, then anything else alphabetically -- mirrors
    _all_filterable_types' own ordering below so "sort by type" groups
    cards in the same order the filter combo already lists them in,
    rather than introducing a second, different notion of type order."""
    if card_type in CARD_TYPES:
        return (0, CARD_TYPES.index(card_type), "")
    if custom_types and card_type in custom_types:
        return (1, custom_types.index(card_type), "")
    return (2, 0, card_type)


# Sentinel item data for the "show every card type" entry in each column's
# type filter combo box -- distinct from any real card-type name (custom
# types are free-text, but never equal to this constant) so "All types" can
# be told apart from a type literally named "All types" if a user ever
# creates one.
FILTER_ALL_TYPES = "\u2014 All types \u2014"

COLUMN_MIME_TYPE = "application/x-whiteboard-column"
COLUMN_WIDTH = 260       # default/"comfortable" column width
# Cap on how wide a single column is ever grown to fill extra window width
# (see MainWindow._apply_column_stretch_width). Deliberately generous
# rather than a tight "reasonable max" -- a tighter cap left visible dead
# space to the right of the last column whenever there were few columns on
# a wide/maximized/ultrawide window, since the stretch logic always fills
# evenly across whatever columns exist and stops growing once every column
# hits this ceiling. 900px still keeps a single very wide column's text
# measure reasonable (cards word-wrap regardless), while being high enough
# that this ceiling is essentially never the reason width goes unused.
COLUMN_MAX_WIDTH = 900
# Smallest a column is ever shrunk to when the window is narrower than the
# combined comfortable width of all columns (see
# MainWindow._apply_column_stretch_width). Below this, cards/labels would no
# longer be legible, so the board switches to horizontal scrolling instead
# of shrinking further -- this is the floor, not a typical width.
COLUMN_MIN_WIDTH = 220
# Extra right-hand margin reserved inside cards_container so
# FeatureCardWidget's drop shadow (blur radius 14, see card_widget
# ._apply_shadow) has room to render instead of being clipped by the
# container/scroll-viewport edge. Small enough to be visually
# unnoticeable as reduced card width, comfortably larger than the
# shadow's own blur radius.
CARD_SHADOW_MARGIN = 16


class DropIndicator(QFrame):
    """A thin horizontal line shown where a card will land."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setObjectName("ColumnDropIndicator")
        self.hide()


class ColumnDropIndicatorV(QFrame):
    """A thin vertical line shown where a dragged column will land."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(3)
        self.setObjectName("ColumnDropIndicator")
        self.hide()


class ColumnWidget(QFrame):
    cardDropped = Signal(str, str, int)   # card_id, column_id, index
    addCardRequested = Signal(str)        # column_id
    quickAddRequested = Signal(str, str)  # column_id, title
    cardEditRequested = Signal(str)       # card_id
    cardDeleteRequested = Signal(str)     # card_id
    cardDuplicateRequested = Signal(str)  # card_id
    cardSelectRequested = Signal(str, bool, bool)  # card_id, shift, ctrl
    cardCheckToggled = Signal(str, bool)           # card_id, checked
    cardTypeChangeRequested = Signal(str, str)     # card_id, new_type
    cardPriorityChangeRequested = Signal(str, str)  # card_id, new_priority
    cardGroupDropped = Signal(list, str, int)      # card_ids, column_id, index
    renameRequested = Signal(str)         # column_id
    deleteRequested = Signal(str)         # column_id
    moveLeftRequested = Signal(str)       # column_id
    moveRightRequested = Signal(str)      # column_id
    columnDropped = Signal(str, str, bool)  # dragged_column_id, target_column_id, insert_before
    sortStateChanged = Signal(str, object, bool)  # column_id, sort_key, descending

    def __init__(self, column: Column, parent=None, custom_types=None, reduced_motion: bool = False,
                 accent_index: int = 0, initial_sort_key=SORT_BOARD_ORDER,
                 initial_sort_descending: bool = False):
        super().__init__(parent)
        self.column = column
        self.custom_types = custom_types or []
        # Which card type this column is currently filtered to show, or
        # None for "show every type" (the default). Session/UI-only: not
        # part of Column/Project's persisted schema, since a filter is a
        # local viewing preference rather than board data, matching how
        # e.g. scroll position isn't persisted either. Reset naturally
        # whenever the column is torn down and rebuilt (project switch,
        # column add/remove/reorder), same as any other view-only widget
        # state in this class.
        self._type_filter = None
        # Display-only sort state for this column (see SORT_BY_TYPE/
        # SORT_BY_PRIORITY above): never touches card.order, drag/drop,
        # or what's saved to disk -- purely a rendering choice, same
        # contract as the type filter. None means "board order" (no sort
        # applied, i.e. the normal drag/drop-defined order). Unlike the
        # type filter, this column's chosen sort mode/direction is kept
        # by MainWindow per (project, column) across rebuilds -- see
        # initial_sort_key/initial_sort_descending below and
        # sortStateChanged -- so switching projects and back restores
        # each column's previously selected sort instead of resetting it.
        self._sort_key = initial_sort_key
        self._sort_descending = initial_sort_descending
        self.setObjectName("ColumnFrame")
        self.setAcceptDrops(True)
        self.setFixedWidth(COLUMN_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        # Accent stripe color for this column, cycled by its position (see
        # models.column_accent_color) -- applied via _apply_accent_color()
        # below rather than baked into the #ColumnFrame QSS rule directly,
        # since each column needs its own color while sharing the same
        # object name/stylesheet selector.
        self._accent_color = column_accent_color(accent_index)
        self._all_cards = []       # full (unfiltered) card list, set by set_cards()
        self._show_numbers = True
        self._selected_card_ids = set()  # kept in sync by MainWindow via set_selected_ids()
        # This stays QSizePolicy.Fixed with a width set via setFixedWidth():
        # MainWindow._apply_column_stretch_width() is the single place that
        # ever changes that fixed width (to redistribute extra window
        # width evenly across columns on window resize -- see there for
        # why an actual size-policy change wasn't used instead). Keeping
        # it Fixed rather than Expanding/Preferred avoids reopening the
        # careful fixed-width drag/drop-position math in this file
        # (_index_for_y, indicator placement, etc.), none of which
        # assumes anything about *how* the width was chosen, only that it
        # doesn't change out from under a layout pass mid-computation.

        self._drag_start_pos = QPoint()
        self._indicator_index = None  # currently shown drop-indicator index, or None
        # Current card width, kept in sync with this column's own width by
        # set_column_width() -- see there and FeatureCardWidget.set_card_width.
        self._card_width = max(60, COLUMN_WIDTH - 20 - CARD_SHADOW_MARGIN)

        self._build_ui(reduced_motion=reduced_motion)
        self._card_widgets = {}  # card_id -> FeatureCardWidget
        self._empty_state_widget = None  # placeholder shown when there are no visible cards
        self._apply_accent_color()

    def set_reduced_motion(self, enabled: bool):
        self._scroll_area.set_reduced_motion(enabled)

    def set_always_highlight_drop_zone(self, enabled: bool):
        """Accessibility: keep the column's drop-zone outline visible at
        all times (see #ColumnDropZone[alwaysHighlighted] in styles.py)
        instead of only flashing it on for the duration of an active drag
        (dragEnterEvent/dragLeaveEvent's own "dragOver" property, which
        this leaves untouched -- the two properties combine additively in
        QSS, so an in-progress drag's own highlight still layers on top
        as normal either way)."""
        self.cards_container.setProperty("alwaysHighlighted", enabled)
        self.cards_container.style().unpolish(self.cards_container)
        self.cards_container.style().polish(self.cards_container)

    def set_column_width(self, width: int):
        """Called by MainWindow to redistribute window width evenly across
        visible columns on resize (see
        MainWindow._apply_column_stretch_width): grows columns to fill
        extra width instead of leaving it as unused scrollable space, and
        shrinks columns (down to COLUMN_MIN_WIDTH) instead of clipping
        columns out of view when the window is narrower than their
        combined comfortable width. Card width is kept in sync with the
        column's own inner content width so cards never overflow a
        shrunk column or leave dead space in a grown one."""
        if width != self.width():
            self.setFixedWidth(width)
        # Inner content width = column width minus its own left+right
        # margins (see outer.setContentsMargins in _build_ui below) minus
        # CARD_SHADOW_MARGIN, which cards_layout reserves on the right so
        # each card's drop shadow has room to render instead of being
        # clipped (see cards_layout.setContentsMargins in _build_ui).
        card_width = max(60, width - 20 - CARD_SHADOW_MARGIN)
        if card_width != self._card_width:
            self._card_width = card_width
            for w in self._card_widgets.values():
                w.set_card_width(card_width)

    def _build_ui(self, reduced_motion: bool = False):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        header_row = QHBoxLayout()
        actions_row = QHBoxLayout()
        actions_row.addStretch()

        self.drag_handle = QLabel("\u2807")  # vertical dots grip, drag column by this
        self.drag_handle.setObjectName("ColumnDragHandle")
        self.drag_handle.setCursor(Qt.OpenHandCursor)
        self.drag_handle.setToolTip("\U0001F91A Drag to reorder this column")
        header_row.addWidget(self.drag_handle)

        self.header_label = QLabel(self.column.name)
        self.header_label.setTextFormat(Qt.PlainText)
        self.header_label.setObjectName("ColumnHeader")
        self.header_label.setWordWrap(True)
        self.header_label.setToolTip(self.column.name)
        self.header_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.header_label.setCursor(Qt.PointingHandCursor)
        self.header_label.mouseDoubleClickEvent = lambda e: self.renameRequested.emit(self.column.id)
        header_row.addWidget(self.header_label, 1)

        self.count_label = QLabel("0")
        self.count_label.setObjectName("ColumnCount")
        header_row.addWidget(self.count_label)
        header_row.addStretch()

        self.add_button = QToolButton()
        self.add_button.setObjectName("AddCardButton")
        self.add_button.setText("+")
        self.add_button.setToolTip("\u2795 Add a card to this column")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.setAutoRaise(True)
        self.add_button.clicked.connect(lambda: self.addCardRequested.emit(self.column.id))
        actions_row.addWidget(self.add_button)

        self.left_btn = QToolButton()
        self.left_btn.setText("\u2190")
        self.left_btn.setToolTip("Move this column left")
        self.left_btn.setCursor(Qt.PointingHandCursor)
        self.left_btn.setAutoRaise(True)
        self.left_btn.clicked.connect(lambda: self.moveLeftRequested.emit(self.column.id))
        actions_row.addWidget(self.left_btn)

        self.right_btn = QToolButton()
        self.right_btn.setText("\u2192")
        self.right_btn.setToolTip("Move this column right")
        self.right_btn.setCursor(Qt.PointingHandCursor)
        self.right_btn.setAutoRaise(True)
        self.right_btn.clicked.connect(lambda: self.moveRightRequested.emit(self.column.id))
        actions_row.addWidget(self.right_btn)

        self.menu_btn = QToolButton()
        self.menu_btn.setText("\u22EF")
        self.menu_btn.setToolTip("More options")
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.setAutoRaise(True)
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        col_menu = QMenu(self.menu_btn)
        rename_action = col_menu.addAction("\u270F\uFE0F Rename Column")
        rename_action.triggered.connect(lambda: self.renameRequested.emit(self.column.id))
        delete_action = col_menu.addAction("\U0001F5D1\uFE0F Delete Column")
        delete_action.triggered.connect(lambda: self.deleteRequested.emit(self.column.id))
        self.menu_btn.setMenu(col_menu)
        actions_row.addWidget(self.menu_btn)

        outer.addLayout(header_row)
        outer.addLayout(actions_row)

        # Inline quick-add: type a title and press Enter to append a card
        # to this column directly, without opening the full CardDialog.
        # The new card always uses the default type ("Add") and no
        # description -- same as clicking the "+" button used to require
        # a dialog for, this just skips that dialog for the common case of
        # "I just want to jot a title down". The field clears itself (but
        # keeps focus) after each Enter, so several titles can be added
        # back-to-back without re-clicking into the field. Full editing
        # (type, description, etc.) is still available afterward via the
        # card's own Edit action, so this never removes any capability,
        # only adds a faster path for the common case.
        self.quick_add_edit = QLineEdit()
        self.quick_add_edit.setObjectName("QuickAddEdit")
        self.quick_add_edit.setPlaceholderText("\u2795 Quick add\u2026 (Enter)")
        self.quick_add_edit.setClearButtonEnabled(False)
        self.quick_add_edit.returnPressed.connect(self._on_quick_add_submitted)
        outer.addWidget(self.quick_add_edit)

        # Type filter: a compact combo box that limits this column's own
        # card list to a single card type (or "All types", the default).
        # Filtering is purely a rendering choice made in set_cards() below
        # -- it never touches project.cards or column.id, so it can't
        # affect drag/drop indices, persistence, or any other column.
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        self.filter_combo = QComboBox()
        self.filter_combo.setObjectName("ColumnTypeFilter")
        self.filter_combo.setCursor(Qt.PointingHandCursor)
        self._populate_filter_combo()
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.filter_combo, 1)
        outer.addLayout(filter_row)

        # Sort: a compact combo (Board order / Type / Priority) plus a
        # small ascending/descending toggle button, sitting right below
        # the type filter as another small, understated per-column
        # control. Purely a rendering choice, same as the filter above --
        # it re-orders only what's displayed in this column, never
        # card.order, so drag/drop indices and persistence are completely
        # unaffected by whatever sort is currently applied.
        sort_row = QHBoxLayout()
        sort_row.setContentsMargins(0, 0, 0, 0)
        sort_row.setSpacing(4)
        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("ColumnTypeFilter")
        self.sort_combo.setCursor(Qt.PointingHandCursor)
        self.sort_combo.addItem("\U0001F51D Board order", SORT_BOARD_ORDER)
        self.sort_combo.addItem("\U0001F3F7\uFE0F Sort by type", SORT_BY_TYPE)
        self.sort_combo.addItem("\U0001F6A9 Sort by priority", SORT_BY_PRIORITY)
        # Reflect this column's restored sort state (see __init__'s
        # initial_sort_key), rather than always starting at "Board
        # order", so rebuilding the column (project switch, column
        # add/remove/reorder) doesn't visually reset a sort the user had
        # already chosen for it.
        restored_index = self.sort_combo.findData(self._sort_key)
        self.sort_combo.setCurrentIndex(restored_index if restored_index >= 0 else 0)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        sort_row.addWidget(self.sort_combo, 1)

        self.sort_dir_btn = QToolButton()
        self.sort_dir_btn.setObjectName("ColumnSortDirButton")
        self.sort_dir_btn.setText("\u2193" if self._sort_descending else "\u2191")
        self.sort_dir_btn.setToolTip(
            "Sort descending (click to switch to ascending)"
            if self._sort_descending
            else "Sort ascending (click to switch to descending)"
        )
        self.sort_dir_btn.setCursor(Qt.PointingHandCursor)
        self.sort_dir_btn.setAutoRaise(True)
        self.sort_dir_btn.setEnabled(self._sort_key is not None)  # no-op until a sort is chosen
        self.sort_dir_btn.clicked.connect(self._on_sort_dir_toggled)
        sort_row.addWidget(self.sort_dir_btn)
        outer.addLayout(sort_row)

        self.cards_container = QWidget()
        self.cards_container.setObjectName("ColumnDropZone")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setAlignment(Qt.AlignTop)
        # Right margin reserves room for FeatureCardWidget's drop shadow
        # (QGraphicsDropShadowEffect, blur radius 14) to render fully.
        # Cards are setFixedWidth() to exactly fill this container's inner
        # width (see set_column_width() below), so with a zero right
        # margin the shadow's right edge had nowhere to paint and was cut
        # off by this container/the scroll viewport. CARD_SHADOW_MARGIN is
        # subtracted from card width to compensate, so the card's own left
        # edge (and header/filter row above it) are unaffected -- only the
        # shadow gets its clipping room back.
        self.cards_layout.setContentsMargins(0, 0, CARD_SHADOW_MARGIN, 0)
        self.cards_layout.setSpacing(8)
        # No trailing stretch here: the cards_container is sized to its
        # content (see set_cards -> _sync_container_height) and sits inside
        # a scroll area, so a stretch spacer would just add dead space
        # below the last card instead of the scroll area doing so.

        # Cards live inside a scroll area so a column with more cards than
        # fit on screen scrolls vertically instead of pushing the window
        # (or other columns) to grow, and so a column with few cards has no
        # leftover dead space below its last card -- the scroll area's
        # viewport is exactly the column's available height, but the
        # cards_container itself (what actually scrolls) is only ever as
        # tall as its content.
        self._scroll_area = SmoothVScrollArea(reduced_motion=reduced_motion)
        self._scroll_area.setObjectName("ColumnScrollArea")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setWidget(self.cards_container)
        # Drops need to land on the column as a whole (including empty
        # space below the last card / the scroll viewport), so the scroll
        # area and its viewport forward drag/drop events up to this
        # ColumnWidget rather than accepting them, which QScrollArea's
        # QAbstractScrollArea base would otherwise silently swallow.
        self._scroll_area.setAcceptDrops(False)
        self._scroll_area.viewport().setAcceptDrops(False)
        outer.addWidget(self._scroll_area, 1)

        # Parented to self (like _col_indicator_left below) so Qt owns and
        # destroys it along with the rest of this ColumnWidget's children
        # when the column is torn down (see MainWindow._load_active_project,
        # which calls setParent(None) + deleteLater() on the whole
        # ColumnWidget). Without an explicit parent here, this widget only
        # ever gets a Qt parent transiently while inserted into
        # cards_layout during a drag; if the column is rebuilt while no
        # drag indicator is showing (the common case), the old DropIndicator
        # had no parent and was never actually deleted -- a small orphaned
        # QWidget leaked on every project switch/reload and every add/edit/
        # delete/drag action that rebuilds this column.
        self._indicator = DropIndicator(self)
        self._col_indicator_left = ColumnDropIndicatorV(self)
        self._col_indicator_left.hide()

        # Drag handle initiates a column-level drag (distinct mime type from cards).
        self.drag_handle.mousePressEvent = self._handle_press
        self.drag_handle.mouseMoveEvent = self._handle_move
        self.header_label.mousePressEvent = self._handle_press
        self.header_label.mouseMoveEvent = self._handle_move

    def _on_quick_add_submitted(self):
        """Enter pressed in the inline quick-add field: emit the new
        card's title for MainWindow to actually create the card (keeping
        all card-creation logic -- ordering, persistence, custom types --
        in one place rather than duplicating it here), then clear the
        field but keep focus so another title can be typed immediately.
        A blank/whitespace-only title is a no-op (nothing emitted, field
        left as-is) rather than creating an empty card, matching the same
        "title required" validation CardDialog already enforces."""
        title = self.quick_add_edit.text().strip()
        if not title:
            return
        self.quick_add_edit.clear()
        self.quickAddRequested.emit(self.column.id, title)

    def _handle_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()

    def _handle_move(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < 12:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(COLUMN_MIME_TYPE, self.column.id.encode("utf-8"))
        drag.setMimeData(mime)
        pixmap = self.grab()
        drag.setPixmap(pixmap.scaledToWidth(160, Qt.SmoothTransformation))
        # Drag-feedback border is applied via _apply_accent_color(dragging=
        # True) rather than the setProperty()+unpolish/polish QSS-state
        # toggle this used before: that mechanism relies on the app-wide
        # #ColumnFrame[dragging="true"] stylesheet rule, but this column
        # now also carries its own inline per-instance stylesheet for the
        # accent stripe (see _apply_accent_color), and an inline
        # stylesheet always wins over a QSS selector rule for the same
        # widget -- so the old dragging-state rule would otherwise never
        # actually be visible once an accent color was added.
        self._apply_accent_color(dragging=True)
        drag.exec(Qt.MoveAction)
        self._apply_accent_color(dragging=False)

    # ---------------------------------------------------------- rendering
    def clear_cards(self):
        for widget in list(self._card_widgets.values()):
            self.cards_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self._card_widgets.clear()
        if self._indicator.parent() is self.cards_container:
            self.cards_layout.removeWidget(self._indicator)
        self._indicator_index = None
        self._clear_empty_state()

    def _clear_empty_state(self):
        """Tear down the empty-state placeholder (illustration + CTA), if
        one is currently shown. Parented to cards_container like every
        card widget, so it's torn down the same way on every re-render
        rather than needing its own separate lifecycle bookkeeping."""
        widget = getattr(self, "_empty_state_widget", None)
        if widget is not None:
            self.cards_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
            self._empty_state_widget = None

    def set_selected_ids(self, selected_ids):
        """Update which cards render as selected, without a full
        rebuild -- called by MainWindow whenever the multi-selection
        changes (a card click, Escape, bulk action completing, etc.).
        Only touches currently-visible card widgets directly (cheap);
        cards not currently rendered (filtered out, or in a column not
        yet built) simply pick up the right state next time they're
        (re)rendered via _render_filtered_cards, which also consults
        this set."""
        self._selected_card_ids = set(selected_ids)
        for card_id, widget in self._card_widgets.items():
            widget.set_selected(card_id in self._selected_card_ids)
            widget.set_selection_context(self._selected_card_ids)

    def set_cards(self, cards, show_numbers: bool = True):
        """cards: list of Card objects already sorted by order (the full,
        unfiltered list for this column -- filtering by type, if any, is
        applied here for display only, so the underlying order/positions
        used by drag-and-drop and persistence are never affected by
        whatever the filter is currently set to)."""
        self._all_cards = cards
        self._show_numbers = show_numbers
        # Re-populate the filter combo against the new card list before
        # rendering: MainWindow._refresh_columns calls
        # update_custom_types() (which also repopulates the combo, but
        # against the *previous* card list) before this method runs, so a
        # card whose type just became newly present -- or newly absent --
        # in this column wouldn't otherwise show up in the filter options
        # until some later, unrelated refresh happened to run.
        self._populate_filter_combo()
        self._render_filtered_cards()

    def _render_filtered_cards(self):
        """Re-render this column's card widgets from the last cards passed
        to set_cards(), applying the active type filter (if any). Numbers
        (see show_numbers) are assigned by *visible* position, matching
        what's actually on screen, rather than the card's position in the
        column's full, unfiltered list."""
        timer = getattr(self, "_scroll_restore_timer", None)
        scroll_value = (self._scroll_restore_value if timer and timer.isActive()
                        else self._scroll_area.verticalScrollBar().value())
        self._scroll_area.stop_scrolling()
        self.clear_cards()
        cards = getattr(self, "_all_cards", []) or []
        show_numbers = getattr(self, "_show_numbers", True)
        if self._type_filter:
            cards = [c for c in cards if c.card_type == self._type_filter]
        cards = self._sorted_for_display(cards)

        for i, card in enumerate(cards):
            number = (i + 1) if show_numbers else None
            w = FeatureCardWidget(
                card, self.cards_container, number=number,
                custom_types=self.custom_types, width=self._card_width,
                selected=card.id in self._selected_card_ids,
            )
            w.editRequested.connect(self.cardEditRequested.emit)
            w.deleteRequested.connect(self.cardDeleteRequested.emit)
            w.duplicateRequested.connect(self.cardDuplicateRequested.emit)
            w.selectRequested.connect(self.cardSelectRequested.emit)
            w.checkToggled.connect(self.cardCheckToggled.emit)
            w.typeChangeRequested.connect(self.cardTypeChangeRequested.emit)
            w.priorityChangeRequested.connect(self.cardPriorityChangeRequested.emit)
            w.set_selection_context(self._selected_card_ids)
            self.cards_layout.addWidget(w)
            w.show()
            self._card_widgets[card.id] = w

        if not cards:
            self._show_empty_state(filtered=bool(self._type_filter))

        # Deliberately no trailing stretch: cards_container sits inside a
        # scroll area (see _build_ui), so its height should hug its content
        # (tight below the last card) rather than being padded out to fill
        # whatever vertical space the column happens to have -- a stretch
        # here would create exactly the dead space this view is meant to
        # avoid for short columns, while making no difference for columns
        # long enough to scroll.
        # Count label shows the *visible* (filtered) count, with the total
        # alongside whenever a filter is narrowing what's shown, so
        # filtering never reads as if cards were deleted.
        self.cards_layout.activate()
        if not hasattr(self, "_scroll_restore_timer"):
            self._scroll_restore_timer = QTimer(self)
            self._scroll_restore_timer.setSingleShot(True)
            self._scroll_restore_timer.timeout.connect(self._restore_scroll_position)
        self._scroll_restore_value = scroll_value
        self._scroll_restore_timer.start(0)
        total = len(getattr(self, "_all_cards", []) or [])
        if self._type_filter and total != len(cards):
            self.count_label.setText(f"{len(cards)}/{total}")
        else:
            self.count_label.setText(str(total))

    def _restore_scroll_position(self):
        self._scroll_area.verticalScrollBar().setValue(self._scroll_restore_value)

    def _show_empty_state(self, filtered: bool = False):
        """Build and insert the empty-state placeholder (illustration +
        message + \"Add one\" CTA) shown when this column has no visible
        cards. filtered distinguishes "this column has cards but the
        active type filter hides all of them" (no CTA -- adding a card
        wouldn't even show up under the current filter) from "this
        column truly has no cards yet" (CTA offered). Rebuilt on every
        _render_filtered_cards() call like the card widgets themselves,
        so it never goes stale across a filter change, card add/delete,
        or project switch."""
        self._clear_empty_state()
        host = QWidget(self.cards_container)
        host.setObjectName("ColumnEmptyState")
        layout = QVBoxLayout(host)
        layout.setContentsMargins(8, 24, 8, 24)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)

        icon = QLabel("\U0001F5C2\uFE0F" if not filtered else "\U0001F50D")
        icon.setObjectName("ColumnEmptyStateIcon")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        if filtered:
            message = QLabel("No cards match this filter")
        else:
            message = QLabel("No cards yet")
        message.setObjectName("ColumnEmptyStateLabel")
        message.setAlignment(Qt.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message)

        if not filtered:
            cta = QToolButton()
            cta.setObjectName("ColumnEmptyStateCta")
            cta.setText("\u2795 Add one")
            cta.setCursor(Qt.PointingHandCursor)
            cta.setAutoRaise(True)
            cta.clicked.connect(lambda: self.addCardRequested.emit(self.column.id))
            layout.addWidget(cta, 0, Qt.AlignCenter)

        self.cards_layout.addWidget(host)
        self._empty_state_widget = host

    def update_name(self, name: str):
        self.column.name = name
        self.header_label.setText(name)

    def update_custom_types(self, custom_types):
        """Keep this column's known custom card types in sync. Needed
        because a new custom type can be created from the Add/Edit Card
        dialog, which only re-renders the affected column(s) (see
        MainWindow._refresh_columns) rather than rebuilding every
        ColumnWidget from scratch -- without this, cards using a
        just-created type would render with the fallback color instead
        of their assigned palette color until the project is reloaded."""
        self.custom_types = custom_types or []
        # New custom types may have appeared since the filter combo was
        # last populated -- re-populate it (preserving the current
        # selection when possible) so a freshly created type is filterable
        # without needing a full column rebuild.
        self._populate_filter_combo()

    # ------------------------------------------------------------- filter
    def _all_filterable_types(self):
        """Card types this column's cards actually use, in a stable order
        (built-ins first as declared in CARD_TYPES, then this column's
        known custom types) -- not every type in the whole app, so a
        column's filter list doesn't fill up with types that column has
        no cards of."""
        present = {c.card_type for c in (getattr(self, "_all_cards", []) or [])}
        ordered = [t for t in CARD_TYPES if t in present]
        for t in self.custom_types:
            if t in present and t not in ordered:
                ordered.append(t)
        # Catch any card_type not in CARD_TYPES or this column's known
        # custom types (e.g. a type from a hand-edited/older file, or one
        # only a *different* column has registered) so every card in this
        # column is always reachable via the filter.
        for t in sorted(present):
            if t not in ordered:
                ordered.append(t)
        return ordered

    def _populate_filter_combo(self):
        combo = getattr(self, "filter_combo", None)
        if combo is None:
            return
        previous = self._type_filter
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(f"\U0001F3F7\uFE0F {FILTER_ALL_TYPES}", None)
        for t in self._all_filterable_types():
            combo.addItem(t, t)
        # Restore the previous selection if that type is still available
        # in this column; otherwise fall back to "All types" rather than
        # silently keeping a filter active for a type no longer present
        # (e.g. the last card of that type in this column was deleted or
        # dragged away).
        restore_index = 0
        if previous is not None:
            idx = combo.findData(previous)
            if idx >= 0:
                restore_index = idx
            else:
                previous = None
        combo.setCurrentIndex(restore_index)
        self._type_filter = previous
        combo.blockSignals(False)

    def _on_filter_changed(self, index: int):
        combo = self.filter_combo
        self._type_filter = combo.itemData(index)
        self._render_filtered_cards()

    # --------------------------------------------------------------- sort
    def _on_sort_changed(self, index: int):
        self._sort_key = self.sort_combo.itemData(index)
        self.sort_dir_btn.setEnabled(self._sort_key is not None)
        self._render_filtered_cards()
        self.sortStateChanged.emit(self.column.id, self._sort_key, self._sort_descending)

    def _on_sort_dir_toggled(self):
        self._sort_descending = not self._sort_descending
        self.sort_dir_btn.setText("\u2193" if self._sort_descending else "\u2191")
        self.sort_dir_btn.setToolTip(
            "Sort descending (click to switch to ascending)"
            if self._sort_descending
            else "Sort ascending (click to switch to descending)"
        )
        if self._sort_key is not None:
            self._render_filtered_cards()
        self.sortStateChanged.emit(self.column.id, self._sort_key, self._sort_descending)

    def _sorted_for_display(self, cards):
        """Apply the column's own display-only sort (see _sort_key) on
        top of the board-order list already passed in. Uses Python's
        stable sort, so cards that tie on the chosen key (e.g. several
        cards of the same type) keep their existing relative board order
        rather than being shuffled arbitrarily.

        Each sort mode uses a *secondary* key on the other axis, so cards
        end up grouped together on both dimensions instead of only the
        primary one: sorting by priority groups same-priority cards
        together, and within each priority group, same-type cards sit
        together too (and vice versa for sorting by type). The secondary
        key is intentionally left out of `reverse` -- reversing only the
        primary axis (via reverse=self._sort_descending on the whole
        sorted() call) would also reverse the secondary grouping order,
        which would read as arbitrary rather than a deliberate ascending/
        descending choice the person made only for the primary key. To
        keep the secondary axis in the same ascending order regardless of
        the primary direction, the secondary key's own rank is negated
        when reverse=True rather than relying on sorted()'s reverse flag
        for it.
        """
        if self._sort_key is None:
            return cards
        if self._sort_key == SORT_BY_TYPE:
            def key_fn(c):
                type_key = _type_sort_key(c.card_type, self.custom_types)
                priority_rank = _priority_rank_for_card(c.priority)
                if self._sort_descending:
                    priority_rank = -priority_rank
                return (type_key, priority_rank)
        elif self._sort_key == SORT_BY_PRIORITY:
            def key_fn(c):
                priority_rank = _priority_rank_for_card(c.priority)
                type_key = _type_sort_key(c.card_type, self.custom_types)
                if self._sort_descending:
                    type_key = tuple(
                        -v if isinstance(v, int) else v for v in type_key
                    )
                return (priority_rank, type_key)
        else:
            return cards
        return sorted(cards, key=key_fn, reverse=self._sort_descending)

    # ------------------------------------------------------------- accent
    def _apply_accent_color(self, dragging: bool = False):
        """Paint this column's accent stripe as a left border, via an
        inline per-instance stylesheet -- QSS alone can't parameterize a
        color per-widget-instance from a single shared #ColumnFrame rule,
        since every column shares that same object name/selector.

        An inline stylesheet on this widget takes priority over the
        app-wide QSS's own #ColumnFrame / #ColumnFrame[dragging="true"]
        rules (see styles.py and _handle_move above), so this only sets
        `border-left` here and leaves every other #ColumnFrame property
        (background, radius, and -- while a drag is in progress -- the
        accent-colored full border) to the app stylesheet, by re-stating
        just enough of the dragging-state border here too so the two
        don't fight over which one wins. Called both at column build time
        and from _handle_move (drag start/end), so the accent stripe
        keeps showing (as a left border) even while the existing
        drag-feedback border is active, instead of one silently
        overriding the other."""
        t = styles.theme_colors(self._current_theme_id())
        if dragging:
            self.setStyleSheet(
                f"#ColumnFrame {{ border: 1px solid {t['accent']}; "
                f"border-left: 4px solid {self._accent_color}; }}"
            )
        else:
            self.setStyleSheet(
                f"#ColumnFrame {{ border-left: 4px solid {self._accent_color}; }}"
            )

    def _current_theme_id(self) -> str:
        """Best-effort lookup of the app's active theme id, used only to
        pick the right accent color for the drag-feedback border above.
        Falls back to the default theme if it can't be determined (e.g.
        this column isn't attached to a window yet) -- purely cosmetic,
        never raises."""
        win = self.window()
        storage = getattr(win, "storage", None)
        if storage is not None:
            return storage.get_setting("theme", styles.DEFAULT_THEME)
        return styles.DEFAULT_THEME

    # -------------------------------------------------------------- drag/drop
    def _index_for_y(self, y: int, exclude_card_id: str = None) -> int:
        """Determine target insertion index based on mouse y position.

        exclude_card_id: when reordering within the same column, the card
        being dragged is still present in this column's layout (Qt doesn't
        remove it while the drag is in progress), so it must be skipped
        here to match the backend's insertion index, which is computed
        against the card list with the dragged card already excluded
        (see MainWindow._on_card_dropped). Without this, dropping a card
        just after its own original slot lands one position short of
        where the indicator showed.

        The returned index is a *board-order* insertion index, not a raw
        rendered-widget count: whenever a type filter or "Sort by" is
        active, the on-screen widget order no longer matches board order
        (see _sorted_for_display/_type_filter), but MainWindow always
        inserts at this index into the column's cards sorted by their
        real card.order. Counting rendered widgets directly in that case
        would silently reassign every card's order to the *visual*
        sequence on drop -- corrupting persisted order/drag-drop even
        though sort/filter are documented as display-only. Instead, find
        which card (if any) the drop point falls after on screen, then
        look up that card's own board-order position and insert after
        it -- so a sorted/filtered view can still be dropped into, but
        the drop always lands relative to real board order."""
        target_card_id = None
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            w = item.widget()
            if w is None or not isinstance(w, FeatureCardWidget):
                continue
            if exclude_card_id is not None and w.card.id == exclude_card_id:
                continue
            mid = w.y() + w.height() / 2
            if y < mid:
                target_card_id = w.card.id
                break

        board_cards = [
            c for c in (getattr(self, "_all_cards", None) or [])
            if exclude_card_id is None or c.id != exclude_card_id
        ]
        if target_card_id is None:
            return len(board_cards)
        for idx, c in enumerate(board_cards):
            if c.id == target_card_id:
                return idx
        # Card wasn't found in _all_cards (shouldn't normally happen --
        # every rendered widget comes from _all_cards) -- fall back to
        # appending rather than risking an out-of-range index.
        return len(board_cards)

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(CARD_MIME_TYPE):
            event.acceptProposedAction()
            self.cards_container.setProperty("dragOver", True)
            self.cards_container.style().unpolish(self.cards_container)
            self.cards_container.style().polish(self.cards_container)
        elif md.hasFormat(COLUMN_MIME_TYPE):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(CARD_MIME_TYPE):
            event.acceptProposedAction()
            card_id = bytes(md.data(CARD_MIME_TYPE)).decode("utf-8")
            pos = self.cards_container.mapFrom(self, event.position().toPoint())
            index = self._index_for_y(pos.y(), exclude_card_id=card_id)
            self._show_indicator_at(index)
        elif md.hasFormat(COLUMN_MIME_TYPE):
            event.acceptProposedAction()
            # Show a vertical indicator on the left or right edge depending
            # on which half of this column the cursor is over.
            on_left_half = event.position().toPoint().x() < self.width() / 2
            self._show_column_indicator(on_left_half)

    def dragLeaveEvent(self, event):
        self.cards_container.setProperty("dragOver", False)
        self.cards_container.style().unpolish(self.cards_container)
        self.cards_container.style().polish(self.cards_container)
        self._hide_indicator()
        self._col_indicator_left.hide()

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(CARD_MIME_TYPE):
            card_id = bytes(md.data(CARD_MIME_TYPE)).decode("utf-8")
            pos = self.cards_container.mapFrom(self, event.position().toPoint())
            index = self._index_for_y(pos.y(), exclude_card_id=card_id)
            self._hide_indicator()
            self.cards_container.setProperty("dragOver", False)
            self.cards_container.style().unpolish(self.cards_container)
            self.cards_container.style().polish(self.cards_container)
            event.acceptProposedAction()
            if md.hasFormat(CARD_GROUP_MIME_TYPE):
                # Shift/multi-select group drag: the dragged card carried
                # every selected card's id along (see
                # card_widget.FeatureCardWidget._start_drag). Filter out
                # any blank entries defensively (an empty mime payload
                # would otherwise become a single '' id) and always
                # include the physically-dragged card itself, in case it
                # somehow wasn't part of its own selection snapshot.
                raw = bytes(md.data(CARD_GROUP_MIME_TYPE)).decode("utf-8")
                group_ids = [g for g in raw.split(",") if g]
                if card_id not in group_ids:
                    group_ids.append(card_id)
                if len(group_ids) > 1:
                    self.cardGroupDropped.emit(group_ids, self.column.id, index)
                else:
                    self.cardDropped.emit(card_id, self.column.id, index)
            else:
                self.cardDropped.emit(card_id, self.column.id, index)
        elif md.hasFormat(COLUMN_MIME_TYPE):
            dragged_id = bytes(md.data(COLUMN_MIME_TYPE)).decode("utf-8")
            insert_before = event.position().toPoint().x() < self.width() / 2
            self._col_indicator_left.hide()
            event.acceptProposedAction()
            if dragged_id != self.column.id:
                self.columnDropped.emit(dragged_id, self.column.id, insert_before)

    def _show_column_indicator(self, on_left: bool):
        self._col_indicator_left.setFixedHeight(self.height())
        x = 0 if on_left else self.width() - 3
        self._col_indicator_left.move(x, 0)
        self._col_indicator_left.show()
        self._col_indicator_left.raise_()

    def _show_indicator_at(self, index: int):
        # dragMoveEvent fires continuously while the mouse moves, but the
        # target index only actually changes occasionally. Skip the
        # remove/insert (and the layout pass it triggers) when the index
        # hasn't moved, instead of relayouting on every mouse-move tick.
        if self._indicator_index == index and self._indicator.isVisible():
            return
        if self._indicator.parent() is self.cards_container:
            self.cards_layout.removeWidget(self._indicator)
        self.cards_layout.insertWidget(index, self._indicator)
        self._indicator.show()
        self._indicator_index = index

    def _hide_indicator(self):
        self._indicator.hide()
        if self._indicator.parent() is self.cards_container:
            self.cards_layout.removeWidget(self._indicator)
        self._indicator_index = None
