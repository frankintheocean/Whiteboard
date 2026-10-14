"""🗒️ Show a card with edit, drag, and selection actions."""
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect, QSizePolicy,
    QToolButton, QMenu, QCheckBox
)
from PySide6.QtCore import Qt, QMimeData, QPoint, Signal, QTimer
from PySide6.QtGui import QDrag, QColor
from safe_html import safe_rich_text

from models import (
    Card, card_type_color, PRIORITY_COLORS, PRIORITY_LEVELS, priority_label, CARD_TYPES,
    readable_text_color, card_type_icon,
)

CARD_MIME_TYPE = "application/x-whiteboard-card"
# Carries the full set of currently-selected card ids (comma-joined,
# utf-8) alongside CARD_MIME_TYPE when the dragged card is itself part of
# a multi-card selection, so a Shift/Ctrl-selected group can be
# drag-dropped together in one gesture instead of one at a time. Absent
# (or containing just the single dragged card) for an ordinary
# single-card drag, so existing single-card drag/drop behavior -- and
# every column/mainwindow code path that only ever knew about
# CARD_MIME_TYPE -- is completely unaffected unless a group is actually
# being dragged.
CARD_GROUP_MIME_TYPE = "application/x-whiteboard-card-group"


class FeatureCardWidget(QFrame):
    # Class-level (not per-instance) since it's a single global preference
    # applied to every card widget alike, mirroring how ColumnWidget's
    # reduced_motion is pushed to existing widgets after construction
    # rather than threaded through __init__ for every card. Kept as a
    # class attribute (vs. an instance flag set per-card) so toggling the
    # setting takes effect immediately for already-built cards with no
    # rebuild needed -- see MainWindow._on_open_settings.
    double_click_opens_card = True
    focus_outlines = True
    # Default-on display setting: render card title/description text in
    # upper case, regardless of how it was typed. Class-level (same
    # reasoning as double_click_opens_card above) so toggling it in
    # Settings takes effect immediately for already-built cards, no
    # rebuild needed. Display-only -- the underlying Card.title/
    # description stored on disk and shown back in the Edit dialog are
    # never modified, so turning this off (or editing a card) always
    # round-trips the text exactly as typed. Plain-text descriptions are
    # upper-cased the same way as titles; rich-text (HTML) descriptions
    # are left as-is (see _set_desc_text) since upper-casing raw HTML
    # would also upper-case tag/attribute text and corrupt the markup.
    uppercase_card_text = True
    """A single draggable card. Emits signals for edit/delete requests."""

    editRequested = Signal(str)     # card_id
    deleteRequested = Signal(str)   # card_id
    duplicateRequested = Signal(str)  # card_id
    # Emitted on a plain/Shift/Ctrl click, before any drag starts, so
    # MainWindow can maintain the cross-column multi-selection set. Not
    # emitted on a double-click (that's handled separately, as Edit) or
    # when the click turns into a drag (selection there is handled by
    # ColumnWidget/MainWindow at drop time instead -- see
    # mouseMoveEvent below, which only fires this for the press itself).
    selectRequested = Signal(str, bool, bool)  # card_id, shift, ctrl
    # Emitted when the card's own checkbox is toggled directly (distinct
    # from selectRequested's click-anywhere-on-the-card gesture): a plain
    # checkbox toggle always just adds/removes this one card from the
    # selection, with no Shift/Ctrl range-or-add semantics, matching how
    # a checkbox is expected to behave regardless of modifier keys.
    checkToggled = Signal(str, bool)  # card_id, checked
    # Emitted when the type badge's own quick-edit menu picks a new type,
    # or the priority badge's picks a new priority -- a fast path to
    # retype/reprioritize a single card without opening the full Edit
    # Card dialog. Both badges remain purely informational display (no
    # signal) when clicked with nothing chosen, e.g. the menu dismissed.
    typeChangeRequested = Signal(str, str)      # card_id, new_type
    priorityChangeRequested = Signal(str, str)  # card_id, new_priority

    def __init__(self, card: Card, parent=None, number: int = None, custom_types=None, width: int = 220,
                 selected: bool = False):
        super().__init__(parent)
        self.card = card
        self.number = number              # 1-based position within its column, or None
        self.custom_types = custom_types or []
        self.setObjectName("FeatureCard")
        self.setFixedWidth(width)
        self.setCursor(Qt.OpenHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)

        self._drag_start_pos: QPoint = QPoint()
        self._drag_active = False
        self._drag_pending = False  # guards against re-entrant mouseMoveEvent scheduling multiple drags
        # Set on mousePressEvent when a plain (no Shift/Ctrl) click lands
        # on a card that's already part of a multi-selection, and the
        # selectRequested emit is deferred to mouseReleaseEvent -- see
        # mousePressEvent/mouseReleaseEvent below for why.
        self._pending_plain_click = False
        self._selected = selected
        # Frozenset of every currently-selected card id (not just this
        # card's own), kept current by ColumnWidget.set_selected_ids ->
        # set_selection_context() below. Only actually read at drag start
        # (see _start_drag) to decide whether this drag should carry the
        # whole selection along -- see CARD_GROUP_MIME_TYPE.
        self._selection_ids_hint = frozenset((card.id,)) if selected else frozenset()

        self._build_ui()
        self._apply_shadow()
        self._apply_selection_frame()

        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def set_selected(self, selected: bool):
        """Called by ColumnWidget to reflect the current multi-selection
        (see MainWindow._selected_card_ids) without needing a full
        rebuild -- selection is view state layered on top of the same
        card widget, not something that changes card.id or requires
        re-parenting."""
        if selected == self._selected:
            return
        self._selected = selected
        self._apply_selection_frame()
        # blockSignals: this is MainWindow pushing selection state down
        # (Shift/Ctrl-click on a *different* card, a bulk action
        # completing, Escape, etc.), not the person toggling this card's
        # own checkbox -- without blocking, setChecked() here would fire
        # _on_checkbox_toggled -> checkToggled, which MainWindow would
        # then read back as a fresh user action and misinterpret (e.g.
        # re-adding a card an Escape just cleared).
        checkbox = getattr(self, "select_checkbox", None)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(selected)
            checkbox.blockSignals(False)

    def _on_checkbox_toggled(self, checked: bool):
        self.checkToggled.emit(self.card.id, checked)

    def _build_type_menu(self):
        """Populate the type badge's quick-change menu with every type
        known to this card's column (built-ins + custom types passed in
        at construction, see custom_types above) -- the same set the full
        Edit Card dialog's own type dropdown offers, minus the "+ New
        Type..." entry, since creating a brand-new type from this compact
        menu would need its own name-entry dialog anyway and the full
        Edit Card dialog already covers that case."""
        menu = QMenu(self.badge)
        # Built-ins first (declared order), then this card's known custom
        # types, then -- defensively -- the card's own current type if it
        # somehow isn't in either list (e.g. a type only a different
        # column has registered), so the menu never silently omits what's
        # already selected.
        ordered = list(CARD_TYPES)
        for t in self.custom_types:
            if t not in ordered:
                ordered.append(t)
        if self.card.card_type not in ordered:
            ordered.append(self.card.card_type)
        for t in ordered:
            action = menu.addAction(t)
            action.setCheckable(True)
            action.setChecked(t == self.card.card_type)
            action.triggered.connect(lambda checked=False, tt=t: self.typeChangeRequested.emit(self.card.id, tt))
        self.badge.setMenu(menu)

    def _build_priority_menu(self):
        """Populate the priority badge's quick-change menu with every
        priority level (see models.PRIORITY_LEVELS/priority_label) plus a
        "None" entry to clear the priority entirely."""
        menu = QMenu(self.priority_badge)
        none_action = menu.addAction("\u2014 None \u2014")
        none_action.setCheckable(True)
        none_action.setChecked(not self.card.priority)
        none_action.triggered.connect(lambda checked=False: self.priorityChangeRequested.emit(self.card.id, ""))
        for level in PRIORITY_LEVELS:
            action = menu.addAction(priority_label(level))
            action.setCheckable(True)
            action.setChecked(level == self.card.priority)
            action.triggered.connect(lambda checked=False, lv=level: self.priorityChangeRequested.emit(self.card.id, lv))
        self.priority_badge.setMenu(menu)

    def set_selection_context(self, all_selected_ids):
        """Called by ColumnWidget.set_selected_ids alongside set_selected()
        so this widget always knows the *full* current selection, not just
        whether it personally is selected -- needed at drag start to
        decide whether to carry the whole group along (see
        CARD_GROUP_MIME_TYPE in _start_drag). Cheap: just stores a
        frozenset reference, no widget/layout work."""
        self._selection_ids_hint = frozenset(all_selected_ids)

    def _apply_selection_frame(self):
        """Selected cards get a visible accent-colored border on top of
        their normal laminated background color, applied as an inline
        stylesheet alongside _apply_color()'s own background-color rule
        (both target #FeatureCard, so they must be combined into one
        setStyleSheet call rather than two separate ones, the second of
        which would otherwise silently replace the first).

        The border is always painted at the same 2px width -- transparent
        when not selected, accent-colored when selected -- rather than
        switching between "no border" and "2px border". A card with no
        border at all is 4px shorter (2px top + 2px bottom) than one with
        a 2px border, so toggling selection used to grow/shrink the
        clicked card and shift every card below it in the column. On a
        scrolled column that shift happened between the two clicks of a
        double-click (the first click selects on press, see
        mousePressEvent), so the second click could land a few pixels off
        and open the wrong card underneath. Keeping the border width
        constant keeps every card's height -- and everything below it --
        fixed regardless of selection state."""
        color = card_type_color(self.card.card_type, self.custom_types)
        border_color = "#0A84FF" if self._selected or (self.hasFocus() and self.focus_outlines) else "transparent"
        self.setStyleSheet(
            f"#FeatureCard {{ background-color: {color}; "
            f"border: 2px solid {border_color}; }}"
        )

    def set_card_width(self, width: int):
        """Called by ColumnWidget.set_column_width() to keep this card's
        width in sync with its (possibly shrunk or grown) column, instead
        of the card staying a fixed 220px regardless of column width."""
        if width != self.width():
            self.setFixedWidth(width)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        top_row = QHBoxLayout()

        # Selection checkbox: an explicit, always-visible way to add this
        # card to the multi-selection, alongside the existing Shift/Ctrl-
        # click gesture on the card body (see mousePressEvent below) --
        # neither replaces the other. Checking one or more boxes puts the
        # board in "N card(s) selected" mode the same way Shift/Ctrl-click
        # does, since both ultimately just add/remove ids from
        # MainWindow's one selection set (see checkToggled below).
        self.select_checkbox = QCheckBox()
        self.select_checkbox.setObjectName("CardSelectCheckbox")
        self.select_checkbox.setCursor(Qt.PointingHandCursor)
        self.select_checkbox.setChecked(self._selected)
        self.select_checkbox.setToolTip("Select this card")
        # Larger click target than the checkbox's own small visual
        # indicator (see #CardSelectCheckbox::indicator in styles.py):
        # padding around the indicator grows the checkbox's actual
        # clickable rectangle without changing how big the checkmark
        # square itself looks, so a click slightly off the tiny drawn
        # square still lands on the checkbox instead of falling through
        # to the card body's own click-to-select handling underneath.
        self.select_checkbox.setContentsMargins(4, 4, 4, 4)
        # stateChanged (not clicked/toggled) so setChecked() calls from
        # set_selected() below -- e.g. selecting via Shift/Ctrl-click, or
        # a bulk action clearing the selection -- don't loop back through
        # here; toggled by mouse/keyboard vs set programmatically both
        # reach this handler, so it's blocked around programmatic updates
        # in set_selected() instead (see there).
        self.select_checkbox.toggled.connect(self._on_checkbox_toggled)
        top_row.addWidget(self.select_checkbox)

        # Type badge: a small flat QToolButton rather than a plain QLabel,
        # so it (a) gets its own real clickable hit area -- padded well
        # beyond the visible pill via #CardTypeBadge's QSS padding, see
        # styles.py -- and (b) can offer a quick "change type" menu right
        # from the card face, without needing to open the full Edit Card
        # dialog just to retype a card. A QToolButton (not QPushButton)
        # keeps it visually flat/unbordered like the label it replaces;
        # InstantPopup means a click always opens the menu directly, and
        # QToolButton (unlike QLabel) is a real widget in the focus/event
        # chain, so its own mousePressEvent consumes the click instead of
        # it falling through to FeatureCardWidget's card-body handler
        # underneath (which would otherwise select/drag the card instead
        # of hitting the badge).
        self.badge = QToolButton()
        self.badge.setObjectName("CardTypeBadge")
        self.badge.setToolButtonStyle(Qt.ToolButtonTextOnly)
        # Prefix the badge text with a color-blind-safe glyph (see
        # models.card_type_icon) so the type is still identifiable by
        # shape/symbol alone, not just the badge's background color --
        # color and text are both left exactly as they were.
        type_icon = card_type_icon(self.card.card_type, self.custom_types)
        self.badge.setText(f"{type_icon} {self.card.card_type.upper()}")
        self.badge.setToolTip(f"Type: {self.card.card_type}. Click to change.")
        self.badge.setCursor(Qt.PointingHandCursor)
        self.badge.setAutoRaise(True)
        self.badge.setPopupMode(QToolButton.InstantPopup)
        self._build_type_menu()
        type_row = QHBoxLayout()
        type_row.addWidget(self.badge)
        type_row.addStretch()

        # Priority badge: a small separate badge from the type badge above
        # (see models.PRIORITY_LEVELS) -- only shown when the card actually
        # has a priority set, so cards without one look exactly as they did
        # before this feature existed. Same QToolButton treatment as the
        # type badge above, for the same padded-hit-area + quick-menu
        # reasons -- clicking it offers every priority level (including
        # "None" to clear it) without opening the full Edit Card dialog.
        if self.card.priority:
            self.priority_badge = QToolButton()
            self.priority_badge.setObjectName("CardPriorityBadge")
            self.priority_badge.setToolButtonStyle(Qt.ToolButtonTextOnly)
            self.priority_badge.setText(priority_label(self.card.priority))
            self.priority_badge.setToolTip(f"Priority: {priority_label(self.card.priority)}. Click to change.")
            self.priority_badge.setCursor(Qt.PointingHandCursor)
            self.priority_badge.setAutoRaise(True)
            self.priority_badge.setPopupMode(QToolButton.InstantPopup)
            priority_color = PRIORITY_COLORS.get(self.card.priority, "#8E8E93")
            # Text color is picked per-priority-color (see
            # models.readable_text_color) rather than always white --
            # fixed white text is unreadable on the brighter priority
            # colors (P2's yellow especially, P1's orange too).
            text_color = readable_text_color(priority_color)
            self.priority_badge.setStyleSheet(
                f"background-color: {priority_color}; color: {text_color};"
            )
            self._build_priority_menu()
            priority_row = QHBoxLayout()
            priority_row.addWidget(self.priority_badge)
            priority_row.addStretch()
        else:
            self.priority_badge = None

        top_row.addStretch()
        self.number_label = QLabel(f"#{self.number}" if self.number else "")
        self.number_label.setObjectName("CardNumber")
        top_row.addWidget(self.number_label)

        self.menu_btn = QToolButton()
        self.menu_btn.setObjectName("CardMenuButton")
        self.menu_btn.setText("\u22EF")
        self.menu_btn.setToolTip("More options")
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.setAutoRaise(True)
        # Slightly larger than the button's own glyph so the clickable
        # rectangle has a bit of margin around "\u22EF" -- a click just
        # outside the three dots' own tight glyph bounds used to miss the
        # button entirely and land on the card body underneath instead
        # (selecting the card rather than opening the menu).
        self.menu_btn.setFixedSize(26, 26)
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        card_menu = QMenu(self.menu_btn)
        edit_action = card_menu.addAction("\u270F\uFE0F Edit")
        edit_action.triggered.connect(lambda: self.editRequested.emit(self.card.id))
        duplicate_action = card_menu.addAction("\U0001F4CB Duplicate")
        duplicate_action.triggered.connect(lambda: self.duplicateRequested.emit(self.card.id))
        delete_action = card_menu.addAction("\U0001F5D1\uFE0F Delete")
        delete_action.triggered.connect(lambda: self.deleteRequested.emit(self.card.id))
        self.menu_btn.setMenu(card_menu)
        top_row.addWidget(self.menu_btn)

        layout.addLayout(top_row)
        layout.addLayout(type_row)
        if self.priority_badge is not None:
            layout.addLayout(priority_row)

        title_text = self.card.title
        if FeatureCardWidget.uppercase_card_text and title_text:
            title_text = title_text.upper()
        self.title_label = QLabel(title_text)
        self.title_label.setTextFormat(Qt.PlainText)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f"Card: {self.card.title}")
        self.select_checkbox.setAccessibleName(f"Select {self.card.title}")
        self.title_label.setObjectName("CardTitle")
        self.title_label.setWordWrap(True)
        # Default card text is bold + center-aligned (see #CardTitle in
        # styles.py for the QSS side of this). Set explicitly here too --
        # not just via QSS's qproperty-alignment -- since a card whose
        # description contains rich-text HTML (see _set_desc_text) can
        # carry its own per-run formatting that would otherwise leave
        # alignment to whatever the HTML itself specifies.
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        if self.card.description:
            self.desc_label = QLabel()
            self.desc_label.setObjectName("CardDesc")
            self._set_desc_text(self.desc_label, self.card.description, self.card.description_is_html)
            self.desc_label.setWordWrap(True)
            self.desc_label.setMaximumHeight(60)
            # setAlignment (not just the QSS qproperty-alignment above)
            # covers rich-text descriptions too: QLabel applies this as
            # the QTextDocument's default block alignment, and it's safe
            # to rely on here since RichTextEditor's toolbar (dialogs.py)
            # never exposes a paragraph/line-alignment control of its own
            # that could produce HTML with a conflicting explicit
            # text-align on the block.
            self.desc_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.desc_label)
        else:
            self.desc_label = None

    @staticmethod
    def _set_desc_text(label: QLabel, text: str, is_html: bool):
        if is_html:
            # Rich-text descriptions are never upper-cased here: the
            # stored text is raw HTML (tags/attributes included), and
            # blindly upper-casing it would corrupt the markup itself,
            # not just the visible words. See uppercase_card_text above.
            label.setTextFormat(Qt.RichText)
            label.setText(safe_rich_text(text))
        else:
            if FeatureCardWidget.uppercase_card_text and text:
                text = text.upper()
            label.setTextFormat(Qt.PlainText)
            label.setText(text)

    def _apply_shadow(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 3)
        self.setGraphicsEffect(shadow)

    # -------------------------------------------------------------- Mouse
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            mods = event.modifiers()
            shift = bool(mods & Qt.ShiftModifier)
            ctrl = bool(mods & Qt.ControlModifier)
            # Shift/Ctrl-click still update the selection immediately on
            # press, for visual feedback regardless of whether the mouse
            # moves afterward. A *plain* click/press, however, is only
            # emitted immediately when this card is not already part of
            # the current multi-selection -- selecting just this one card
            # even if the press turns into a drag right after (the drag
            # then moves only this card, matching prior single-card
            # behavior). If this card IS already selected, a plain press
            # must NOT collapse the selection down to just this card yet:
            # doing so on press (as before) destroyed a multi-card
            # selection before mouseMoveEvent/_start_drag ever got a
            # chance to see it, so dragging one selected card among
            # several silently dragged only that one card instead of the
            # whole group. Matches standard file-manager behavior
            # (Explorer/Finder): pressing on an already-selected item
            # keeps the selection intact so it can be dragged as a group;
            # the collapse-to-just-this-card (or deselect, if it was the
            # only thing selected) only happens on release, and only if
            # no drag actually occurred -- see mouseReleaseEvent below.
            self._pending_plain_click = False
            if shift or ctrl or not self._selected:
                self.selectRequested.emit(self.card.id, shift, ctrl)
            else:
                self._pending_plain_click = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.LeftButton
            and getattr(self, "_pending_plain_click", False)
            and not self._drag_pending
        ):
            # The deferred plain click from mousePressEvent above: no drag
            # happened (this card was simply clicked, not dragged), so
            # apply the normal plain-click selection behavior now.
            self.selectRequested.emit(self.card.id, False, False)
        self._pending_plain_click = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._pending_plain_click = False
        self._drag_start_pos = None
        if event.button() == Qt.LeftButton and FeatureCardWidget.double_click_opens_card:
            event.accept()
            self.editRequested.emit(self.card.id)
            return
        super().mouseDoubleClickEvent(event)

    def focusInEvent(self, event):
        self._apply_selection_frame()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._apply_selection_frame()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.editRequested.emit(self.card.id)
            event.accept()
        elif event.key() == Qt.Key_Space:
            self.checkToggled.emit(self.card.id, not self._selected)
            event.accept()
        else:
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is None or not (event.buttons() & Qt.LeftButton):
            return
        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < 10:
            return
        if self._drag_pending or self._drag_active:
            # mouseMoveEvent can fire again before the deferred
            # _start_drag() (scheduled via QTimer.singleShot(0, ...) below)
            # has actually run, since the timer only fires once the event
            # loop is re-entered -- without this guard, fast repeated
            # mouse-move ticks during the same drag gesture would each
            # remove the shadow effect and queue another _start_drag(),
            # stacking multiple QDrag.exec() calls for a single drag.
            return

        # Capture the pixmap now, while the shadow effect is still
        # attached. QWidget.grab() is the safe API for snapshotting a
        # widget that has a live QGraphicsEffect — unlike manually
        # rendering into a QPainter via render(), which can crash.
        pixmap = self.grab()

        # Remove the drop-shadow effect for the duration of the drag.
        # NOTE: setGraphicsEffect(None) makes Qt delete the previous
        # effect's C++ object immediately — Qt graphics effects are
        # single-owner and can't be detached and reattached later. So we
        # must NOT hold onto a reference and reassign it afterward; we
        # simply drop it and build a brand new effect once the drag ends.
        self.setGraphicsEffect(None)

        self._pending_drag_pixmap = pixmap
        self._pending_drag_hotspot = event.position().toPoint()
        self.setCursor(Qt.ClosedHandCursor)
        self._drag_pending = True

        # Defer exec() so the nested event loop does not start
        # synchronously from inside mouseMoveEvent/event delivery.
        QTimer.singleShot(0, self._start_drag)

    def _start_drag(self):
        self._drag_pending = False
        # Defensive guard: if the column was torn down/rebuilt (e.g. a
        # project switch or add/edit/delete refresh) in the brief window
        # between mouseMoveEvent scheduling this call and the deferred
        # QTimer.singleShot(0, ...) actually firing, this widget's
        # underlying Qt C++ object may already be destroyed even though
        # the Python wrapper is still alive -- calling into it would raise
        # "RuntimeError: Internal C++ object already deleted" instead of
        # just quietly doing nothing, which is the correct outcome here
        # since there's no drag to start on a widget that's gone.
        try:
            self.isVisible()
        except RuntimeError:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(CARD_MIME_TYPE, self.card.id.encode("utf-8"))
        # Shift-drag (or any drag) of a card that's part of the current
        # multi-selection carries the whole selection's ids along too, so
        # ColumnWidget/MainWindow can move every selected card together
        # in one drop instead of just the one card physically grabbed.
        # self._selected reflects MainWindow's live selection set (kept
        # in sync via set_selected() on every selection change), so this
        # is always accurate as of drag start with no extra plumbing.
        # Deliberately NOT gated on the Shift key specifically: once
        # several cards are selected (via checkbox, Shift-click, or
        # Ctrl-click), dragging *any* of them moves the group -- Shift is
        # simply the most common way people land in that state, not a
        # separate mode of its own, so a plain drag of an already-
        # selected card behaves the same way.
        if self._selected and len(self._selection_ids_hint) > 1:
            group_ids = ",".join(self._selection_ids_hint)
            mime.setData(CARD_GROUP_MIME_TYPE, group_ids.encode("utf-8"))
        drag.setMimeData(mime)
        drag.setPixmap(self._pending_drag_pixmap)
        drag.setHotSpot(self._pending_drag_hotspot)

        self._drag_active = True
        drag.exec(Qt.MoveAction)

        # Same liveness guard as above: drag.exec() pumps its own nested
        # event loop for the duration of the drag, so it's possible (if
        # rare) for something processed during that loop to tear this
        # widget's column down before exec() returns. Without this check,
        # the cleanup below would run on an already-deleted C++ object.
        try:
            self.isVisible()
        except RuntimeError:
            return
        self._drag_active = False
        drag.deleteLater()
        self.setCursor(Qt.OpenHandCursor)
        # Recreate the shadow effect fresh — the old one no longer
        # exists as a valid C++ object once it was detached.
        self._apply_shadow()

    def contextMenuEvent(self, event):
        # Reuse the same menu built in _build_ui (self.menu_btn.menu())
        # instead of constructing a second, duplicate QMenu here.
        # globalPos() is Qt5-era API; use the Qt6 QPointF-based accessor
        # (already used everywhere else in this file, e.g. mousePressEvent)
        # for consistency and forward-compatibility.
        self.menu_btn.menu().exec(event.globalPosition().toPoint())
