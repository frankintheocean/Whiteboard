"""🗣️ Set card details and app preferences."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QComboBox, QDialogButtonBox, QToolButton,
    QFontComboBox, QSpinBox, QWidget, QTabWidget, QCheckBox, QGridLayout,
    QScrollArea, QFrame, QPushButton, QMessageBox, QSizePolicy, QStyleOptionViewItem
)
from PySide6.QtGui import QFont, QFontMetrics, QTextCharFormat, QTextCursor
from PySide6.QtCore import Qt, Signal, QTimer

from models import CARD_TYPES, PRIORITY_LEVELS, BOARD_TEMPLATES, DEFAULT_TEMPLATE_NAME, priority_label
import styles
import app_meta
import error_log
from safe_html import safe_rich_text


def _apply_pointer_cursor(button_box: QDialogButtonBox):
    """QDialogButtonBox doesn't expose its own cursor to its child
    buttons (each Ok/Cancel button is its own QPushButton underneath),
    so setCursor() on the box itself doesn't reach them -- give every
    button inside it a pointer cursor explicitly, matching every other
    clickable control in the app."""
    for btn in button_box.buttons():
        btn.setCursor(Qt.PointingHandCursor)


class FitPopupComboBox(QComboBox):
    """📋 Show full names, including when the list needs a scrollbar."""

    def showPopup(self):
        view = self.view()
        view.setTextElideMode(Qt.ElideNone)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMaxVisibleItems(12)
        for i in range(self.count()):
            self.setItemData(i, self.itemText(i), Qt.ToolTipRole)
        # Measure after Qt has polished the popup and applied its font.
        super().showPopup()
        view.ensurePolished()
        option = QStyleOptionViewItem()
        option.initFrom(view)
        width = self.width()
        for row in range(self.count()):
            index = self.model().index(row, self.modelColumn(), self.rootModelIndex())
            size = view.itemDelegateForIndex(index).sizeHint(option, index)
            item_font = self.itemData(row, Qt.FontRole) or view.font()
            width = max(width, size.width(), QFontMetrics(item_font).horizontalAdvance(self.itemText(row)) + 32)
        width += view.verticalScrollBar().sizeHint().width() + 2 * view.frameWidth() + 16
        screen = self.screen().availableGeometry()
        container = view.window()
        width = min(width, max(100, screen.width() - 16))
        view.setMinimumWidth(width - 8)
        view.setMaximumWidth(width - 8)
        container.setFixedWidth(width)
        x = max(screen.left() + 8, min(container.x(), screen.right() - width - 7))
        container.move(x, container.y())
        # Very long names can scroll horizontally instead of disappearing.
        view.doItemsLayout()


class RichTextEditor(QWidget):
    """A small rich-text control bar (font, size, bold, italic, underline)
    wired to a QTextEdit. Kept self-contained so CardDialog just drops it
    in."""

    def __init__(self, initial_html_or_text="", is_html=False, parent=None):
        super().__init__(parent)
        self._forced_html = is_html
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        self.font_combo = QFontComboBox()
        self.font_combo.setFixedWidth(150)
        self.font_combo.currentFontChanged.connect(self._set_font_family)
        toolbar.addWidget(self.font_combo)

        self.size_combo = QSpinBox()
        self.size_combo.setObjectName("FontSizeSpin")
        self.size_combo.setRange(8, 48)
        self.size_combo.setValue(12)
        self.size_combo.setFixedWidth(40)
        # Hide the up/down stepper buttons and the boxed border around them
        # (the #FontSizeSpin rule in styles.py drops the QSS border/padding
        # that would otherwise still be painted around the field even with
        # the native buttons off) -- the field is still a normal spin box
        # functionally: type a value, or use the scroll wheel/arrow keys
        # while it has focus.
        self.size_combo.setButtonSymbols(QSpinBox.NoButtons)
        self.size_combo.setFrame(False)
        self.size_combo.setAlignment(Qt.AlignCenter)
        self.size_combo.valueChanged.connect(self._set_font_size)
        toolbar.addWidget(self.size_combo)

        self.bold_btn = QToolButton()
        self.bold_btn.setText("B")
        self.bold_btn.setCheckable(True)
        self.bold_btn.setStyleSheet("font-weight: 700;")
        self.bold_btn.setCursor(Qt.PointingHandCursor)
        self.bold_btn.clicked.connect(self._toggle_bold)
        toolbar.addWidget(self.bold_btn)

        self.italic_btn = QToolButton()
        self.italic_btn.setText("I")
        self.italic_btn.setCheckable(True)
        self.italic_btn.setStyleSheet("font-style: italic;")
        self.italic_btn.setCursor(Qt.PointingHandCursor)
        self.italic_btn.clicked.connect(self._toggle_italic)
        toolbar.addWidget(self.italic_btn)

        self.underline_btn = QToolButton()
        self.underline_btn.setText("U")
        self.underline_btn.setCheckable(True)
        self.underline_btn.setStyleSheet("text-decoration: underline;")
        self.underline_btn.setCursor(Qt.PointingHandCursor)
        self.underline_btn.clicked.connect(self._toggle_underline)
        toolbar.addWidget(self.underline_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Details, notes, acceptance criteria...")
        self.editor.setFixedHeight(110)
        if is_html and initial_html_or_text:
            self.set_html_reexpanding_data_uris(initial_html_or_text)
        elif initial_html_or_text:
            self.editor.setPlainText(initial_html_or_text)
        self.editor.cursorPositionChanged.connect(self._sync_toolbar_to_cursor)
        layout.addWidget(self.editor)

    def _apply_char_format(self, fmt: QTextCharFormat):
        self._forced_html = True
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.editor.mergeCurrentCharFormat(fmt)

    def _set_font_family(self, font: QFont):
        fmt = QTextCharFormat()
        fmt.setFontFamilies([font.family()])
        self._apply_char_format(fmt)

    def _set_font_size(self, size: int):
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        self._apply_char_format(fmt)

    def _toggle_bold(self, checked):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold if checked else QFont.Normal)
        self._apply_char_format(fmt)

    def _toggle_italic(self, checked):
        fmt = QTextCharFormat()
        fmt.setFontItalic(checked)
        self._apply_char_format(fmt)

    def _toggle_underline(self, checked):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(checked)
        self._apply_char_format(fmt)

    def _sync_toolbar_to_cursor(self):
        fmt = self.editor.currentCharFormat()
        self.bold_btn.blockSignals(True)
        self.italic_btn.blockSignals(True)
        self.underline_btn.blockSignals(True)
        self.bold_btn.setChecked(fmt.fontWeight() >= QFont.Bold)
        self.italic_btn.setChecked(fmt.fontItalic())
        self.underline_btn.setChecked(fmt.fontUnderline())
        self.bold_btn.blockSignals(False)
        self.italic_btn.blockSignals(False)
        self.underline_btn.blockSignals(False)

    def has_rich_formatting(self) -> bool:
        """True if the content uses any formatting beyond plain text, so the
        caller knows whether to persist as HTML or as plain text."""
        if self._forced_html:
            return True
        doc = self.editor.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    f = frag.charFormat()
                    if f.fontWeight() >= QFont.Bold or f.fontItalic() or f.fontUnderline():
                        return True
                it += 1
            block = block.next()
        return False

    def to_plain_text(self) -> str:
        return self.editor.toPlainText().strip()

    def to_html(self) -> str:
        return self.editor.toHtml()

    def set_html_reexpanding_data_uris(self, html: str):
        """Load previously saved HTML back into the editor. Named to
        match the save-time counterpart this loads from; any inline
        image resources already embedded in a project file saved by an
        older version load fine since QTextEdit.setHtml decodes data:
        URIs natively, they're just no longer insertable from this
        editor going forward."""
        self.editor.setHtml(safe_rich_text(html))


class CardDialog(QDialog):
    """Dialog for creating or editing a feature card.

    manageTypesRenameRequested/manageTypesDeleteRequested are emitted when
    a rename/delete is confirmed in the "Manage Types..." sub-dialog
    reachable from the Type dropdown (see _open_manage_types_dialog).
    Like ManageCardTypesDialog itself, this CardDialog holds no storage
    access -- both signals are relayed straight through to whatever
    connects to this CardDialog instance (MainWindow), which performs the
    actual cross-project storage mutation and re-save."""

    manageTypesRenameRequested = Signal(str, str)  # old_name, new_name
    manageTypesDeleteRequested = Signal(str)        # name

    def __init__(self, parent=None, title="", description="", description_is_html=False,
                 card_type="Add", priority="", heading="Add Card", available_types=None,
                 type_usage_counts=None):
        super().__init__(parent)
        self.setWindowTitle(heading)
        self.setMinimumWidth(400)

        available_types = available_types or list(CARD_TYPES)
        self._type_usage_counts = type_usage_counts or {}
        self.newCardTypeCreated = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel("Title"))
        self.title_edit = QLineEdit(title)
        self.title_edit.setPlaceholderText("e.g. Add dark mode toggle")
        layout.addWidget(self.title_edit)

        type_priority_row = QHBoxLayout()
        type_col = QVBoxLayout()
        type_col.addWidget(QLabel("Type"))
        self.type_combo = FitPopupComboBox()
        self._available_types = list(available_types)
        self._rebuild_type_combo()
        if card_type in self._available_types:
            self.type_combo.setCurrentText(card_type)
        self.type_combo.activated.connect(self._on_type_activated)
        type_col.addWidget(self.type_combo)
        type_priority_row.addLayout(type_col, 1)

        priority_col = QVBoxLayout()
        priority_col.addWidget(QLabel("Priority"))
        self.priority_combo = FitPopupComboBox()
        self.priority_combo.addItem("\u2014 None \u2014", "")
        for level in PRIORITY_LEVELS:
            self.priority_combo.addItem(priority_label(level), level)
        idx = self.priority_combo.findData(priority)
        self.priority_combo.setCurrentIndex(idx if idx >= 0 else 0)
        priority_col.addWidget(self.priority_combo)
        type_priority_row.addLayout(priority_col, 1)

        layout.addLayout(type_priority_row)

        layout.addWidget(QLabel("Description (optional)"))
        self.rich_editor = RichTextEditor(description, is_html=description_is_html)
        layout.addWidget(self.rich_editor)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        _apply_pointer_cursor(buttons)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.title_edit.setFocus()

    def _rebuild_type_combo(self, select_type=None):
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItems(self._available_types)
        self.type_combo.addItem("+ New Type\u2026")
        self.type_combo.addItem("\U0001F3F7\uFE0F Manage Types\u2026")
        if select_type and select_type in self._available_types:
            self.type_combo.setCurrentText(select_type)
        self.type_combo.blockSignals(False)

    def _on_type_activated(self, index):
        text = self.type_combo.itemText(index)
        if text == "\U0001F3F7\uFE0F Manage Types\u2026":
            self._open_manage_types_dialog()
            return
        if text != "+ New Type\u2026":
            return
        dialog = NewCardTypeDialog(self, existing_types=self._available_types)
        if dialog.exec():
            new_type = dialog.get_value()
            self._available_types.append(new_type)
            self.newCardTypeCreated = new_type  # read by caller after accept()
            self._rebuild_type_combo(select_type=new_type)
        else:
            # Revert selection back to the first type rather than leaving
            # the sentinel "+ New Type..." row selected.
            if self._available_types:
                self.type_combo.setCurrentText(self._available_types[0])

    def _open_manage_types_dialog(self):
        """Opens ManageCardTypesDialog for every type currently on offer
        here -- built-in and custom alike. Rename/delete requests are
        relayed straight up to MainWindow via this dialog's own
        manageTypesRenameRequested/manageTypesDeleteRequested signals,
        since the actual storage mutation touches every project, not
        just whatever card this CardDialog instance happens to be
        editing -- this dialog only needs to refresh its own combo
        afterward so the (possibly renamed/removed) type list it shows
        next stays correct."""
        # Tracked in a single-item list (not a plain local) so the rename
        # handler below can follow the selection to its new name -- e.g.
        # renaming the very type this CardDialog currently has selected
        # should keep it selected under the new name, not silently fall
        # back to the first type once the old name no longer exists in
        # _available_types.
        selection_holder = [self.type_combo.currentText()]
        manage_dialog = ManageCardTypesDialog(
            self, all_types=list(self._available_types), usage_counts=self._type_usage_counts
        )
        manage_dialog.renameRequested.connect(
            lambda old, new: self._on_manage_type_rename(manage_dialog, old, new, selection_holder)
        )
        manage_dialog.deleteRequested.connect(
            lambda name: self._on_manage_type_delete(manage_dialog, name, selection_holder)
        )
        manage_dialog.exec()
        # Whatever the current selection resolved to (unchanged, renamed,
        # or reset because it was the type just deleted) after the manage
        # dialog is closed -- rebuild once more here rather than after
        # every individual rename/delete, so a multi-edit session in the
        # manage dialog only costs one combo rebuild in this dialog, not
        # one per edit.
        select = selection_holder[0] if selection_holder[0] in self._available_types else None
        self._rebuild_type_combo(select_type=select or (self._available_types[0] if self._available_types else None))

    def _on_manage_type_rename(self, manage_dialog, old_name, new_name, selection_holder):
        self.manageTypesRenameRequested.emit(old_name, new_name)
        if old_name in self._available_types:
            self._available_types[self._available_types.index(old_name)] = new_name
        if old_name in self._type_usage_counts:
            self._type_usage_counts[new_name] = self._type_usage_counts.pop(old_name)
        if selection_holder[0] == old_name:
            selection_holder[0] = new_name
        manage_dialog.refresh_types(list(self._available_types), self._type_usage_counts)

    def _on_manage_type_delete(self, manage_dialog, name, selection_holder):
        self.manageTypesDeleteRequested.emit(name)
        if name in self._available_types:
            self._available_types.remove(name)
        self._type_usage_counts.pop(name, None)
        if selection_holder[0] == name:
            selection_holder[0] = None
        manage_dialog.refresh_types(list(self._available_types), self._type_usage_counts)

    def _on_accept(self):
        if not self.title_edit.text().strip():
            self.title_edit.setStyleSheet("border: 1px solid #E0393E;")
            return
        self.accept()

    def get_values(self):
        is_rich = self.rich_editor.has_rich_formatting()
        selected_type = self.type_combo.currentText()
        if selected_type == "+ New Type\u2026":
            # Guard: shouldn't happen since _on_type_activated reverts the
            # selection, but fall back to the first real type just in case.
            selected_type = self._available_types[0] if self._available_types else "Add"
        return {
            "title": self.title_edit.text().strip(),
            "description": self.rich_editor.to_html().strip() if is_rich else self.rich_editor.to_plain_text(),
            "description_is_html": is_rich,
            "card_type": selected_type,
            "priority": self.priority_combo.currentData() or "",
            "new_card_type": self.newCardTypeCreated,
        }


class ManageCardTypesDialog(QDialog):
    """Rename or delete any card type, built-in (Add/Change/Remove/Fix/
    Idea, see models.CARD_TYPES) or custom. Reached from the type
    dropdown in CardDialog, alongside "+ New Type...".

    Holds no storage access itself: renaming/deleting is a cross-project
    action (a type can be in use on cards in projects other than the one
    currently open), so this dialog only collects the request and hands
    it back to MainWindow via renameRequested/deleteRequested, the same
    delegation pattern SettingsDialog uses for clearBoardRequested/
    revertBoardRequested. MainWindow performs the actual storage mutation
    and then calls refresh_types() so this dialog's own list reflects the
    result immediately, without needing to be closed and reopened.

    usage_counts: dict[str, int] mapping each type name to how many
    cards (across every project) currently use it, purely for display --
    e.g. "3 cards" next to a type -- so deleting a heavily-used type
    isn't a surprise."""

    renameRequested = Signal(str, str)  # old_name, new_name
    deleteRequested = Signal(str)       # name

    def __init__(self, parent=None, all_types=None, usage_counts=None):
        super().__init__(parent)
        self.setWindowTitle("\U0001F3F7\uFE0F Manage Card Types")
        self.setMinimumWidth(360)

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        outer.setContentsMargins(20, 20, 20, 20)

        hint = QLabel(
            "Rename or delete any type, built-in or custom. Deleting a "
            "type moves any cards using it to the next remaining type "
            "instead of removing those cards. At least one type must "
            "always remain."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px;")
        outer.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        scroll.setWidget(self._rows_host)
        scroll.setMinimumHeight(180)
        outer.addWidget(scroll, 1)

        self._empty_label = QLabel("No types yet -- create one from the Type dropdown.")
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("font-size: 12px; opacity: 0.7;")
        self._empty_label.hide()
        self._rows_layout.addWidget(self._empty_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        _apply_pointer_cursor(buttons)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)

        self.refresh_types(all_types or [], usage_counts or {})

    def refresh_types(self, all_types, usage_counts=None):
        """Rebuild the row list from the current type list (built-in +
        custom, in the same order the type pickers show them -- see
        storage.Storage.available_card_types). Called once at
        construction, and again by MainWindow right after a rename/
        delete actually lands in storage, so this dialog can stay open
        across multiple edits (rename one type, then delete another)
        without the list ever showing stale names/counts. Delete is
        disabled on whichever row is the last remaining type, since at
        least one type must always exist for cards to fall back to."""
        usage_counts = usage_counts or {}
        # Clear existing rows (but not the empty-state label, re-shown/
        # hidden below rather than torn down and rebuilt every time).
        for i in reversed(range(self._rows_layout.count())):
            item = self._rows_layout.itemAt(i)
            w = item.widget()
            if w is not None and w is not self._empty_label:
                self._rows_layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()

        self._empty_label.setVisible(not all_types)
        only_one_left = len(all_types) <= 1
        for name in all_types:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            count = usage_counts.get(name, 0)
            count_text = f"{count} card{'s' if count != 1 else ''}"
            label = QLabel(f"{name}  \u00b7  {count_text}")
            label.setStyleSheet("font-weight: 600;")
            row_layout.addWidget(label, 1)

            rename_btn = QPushButton("Rename")
            rename_btn.setCursor(Qt.PointingHandCursor)
            rename_btn.clicked.connect(lambda checked=False, n=name: self._on_rename_clicked(n))
            row_layout.addWidget(rename_btn)

            delete_btn = QPushButton("Delete")
            delete_btn.setCursor(Qt.PointingHandCursor)
            delete_btn.setEnabled(not only_one_left)
            delete_btn.setToolTip(
                "At least one card type must always remain" if only_one_left else ""
            )
            delete_btn.clicked.connect(lambda checked=False, n=name: self._on_delete_clicked(n))
            row_layout.addWidget(delete_btn)

            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)

    def _on_rename_clicked(self, name: str):
        dialog = TextPromptDialog(self, heading="Rename Type", label="Type name", initial=name)
        if dialog.exec():
            new_name = dialog.get_value()
            if new_name and new_name != name:
                self.renameRequested.emit(name, new_name)

    def _on_delete_clicked(self, name: str):
        confirm = QMessageBox.question(
            self, "\U0001F5D1\uFE0F Delete Type",
            f"Delete the '{name}' type? Cards using it will be moved to "
            f"the next remaining type instead.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.deleteRequested.emit(name)


class TextPromptDialog(QDialog):
    """Simple single-line text prompt (used for project name, rename column)."""

    def __init__(self, parent=None, heading="Enter value", label="Name", initial=""):
        super().__init__(parent)
        self.setWindowTitle(heading)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel(label))
        self.edit = QLineEdit(initial)
        layout.addWidget(self.edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        _apply_pointer_cursor(buttons)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.edit.setFocus()
        self.edit.selectAll()

    def _on_accept(self):
        if not self.edit.text().strip():
            self.edit.setStyleSheet("border: 1px solid #E0393E;")
            return
        self.accept()

    def get_value(self) -> str:
        return self.edit.text().strip()


class NewProjectDialog(QDialog):
    """New Project prompt: project name plus a starting column template
    (see models.BOARD_TEMPLATES). Separate from TextPromptDialog (used
    elsewhere for plain rename/name-only prompts) since this needs the
    extra template picker; get_value()/get_values() both exist so this
    slots in wherever a name-only result is enough (get_value) as well
    as where the chosen template also matters (get_values)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("\u2795 New Project")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel("Project name"))
        self.edit = QLineEdit()
        layout.addWidget(self.edit)

        layout.addWidget(QLabel("Board template"))
        self.template_combo = FitPopupComboBox()
        for name, columns in BOARD_TEMPLATES:
            preview = " / ".join(columns) if columns else "no starting columns"
            self.template_combo.addItem(name, name)
            self.template_combo.setItemData(
                self.template_combo.count() - 1, f"{name}: {preview}", Qt.ToolTipRole
            )
        default_idx = self.template_combo.findData(DEFAULT_TEMPLATE_NAME)
        self.template_combo.setCurrentIndex(default_idx if default_idx >= 0 else 0)
        layout.addWidget(self.template_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        _apply_pointer_cursor(buttons)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.edit.setFocus()

    def _on_accept(self):
        if not self.edit.text().strip():
            self.edit.setStyleSheet("border: 1px solid #E0393E;")
            return
        self.accept()

    def get_value(self) -> str:
        return self.edit.text().strip()

    def get_values(self) -> dict:
        template_name = self.template_combo.currentData() or DEFAULT_TEMPLATE_NAME
        columns = next(
            (cols for name, cols in BOARD_TEMPLATES if name == template_name),
            list(BOARD_TEMPLATES[0][1]),
        )
        return {"name": self.edit.text().strip(), "columns": list(columns)}


class ThemeSwatch(QFrame):
    """Clickable preview swatch for one theme, used in the Settings dialog."""
    def __init__(self, theme_id: str, label: str, selected: bool, parent=None):
        super().__init__(parent)
        self.theme_id = theme_id
        self.setObjectName("ThemeSwatch")
        self.setProperty("selected", selected)
        self.setFixedSize(96, 64)
        self.setCursor(Qt.PointingHandCursor)
        # Make the swatch keyboard-reachable (Tab) and give it a visible
        # focus state, so "Show a visible focus outline" in Accessibility
        # actually has something to show here, not just on the OK/Cancel
        # buttons and text fields.
        self.setFocusPolicy(Qt.StrongFocus)

        colors = styles.theme_colors(theme_id)
        self.setStyleSheet(
            f"#ThemeSwatch {{ background-color: {colors['bg']}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        bar = QFrame()
        bar.setFixedHeight(14)
        bar.setStyleSheet(f"background-color: {colors['surface']}; border-radius: 3px;")
        layout.addWidget(bar)

        accent = QFrame()
        accent.setFixedHeight(10)
        accent.setFixedWidth(30)
        accent.setStyleSheet(f"background-color: {colors['accent']}; border-radius: 3px;")
        layout.addWidget(accent)

        layout.addStretch()

        name = QLabel(label)
        name.setStyleSheet(f"color: {colors['text']}; font-size: 10px; font-weight: 600; background: transparent;")
        layout.addWidget(name)


class SettingsDialog(QDialog):
    """Settings panel: basic preferences tab + a 10-theme picker tab +
    an accessibility tab + an in-app changelog tab.

    themeApplied is emitted immediately when the user picks a theme swatch,
    so the caller can live-preview it behind the dialog without waiting for
    OK. If the user ends up pressing Cancel, the caller is responsible for
    reverting to the theme that was active when the dialog was opened (see
    MainWindow._on_open_settings).

    clearBoardRequested / revertBoardRequested are emitted from the
    Diagnostics tab's "Clear Board" / "Undo" buttons. The dialog itself
    holds no board data -- it just relays the request and immediately
    re-reads the diagnostics numbers it's given via refresh_diagnostics()
    so the tab reflects the new (post-clear or post-revert) state without
    the whole Settings dialog needing to be closed and reopened."""

    themeApplied = Signal(str)
    clearBoardRequested = Signal()
    revertBoardRequested = Signal()
    clearErrorLogRequested = Signal()
    # Emitted when the new "Manage..." button on the General tab (see
    # basic_layout below) is pressed. Like clearBoardRequested/
    # revertBoardRequested above, this dialog holds no card/type data of
    # its own -- MainWindow owns opening the actual ManageCardTypesDialog
    # (it needs the live custom-types list and per-type usage counts,
    # which only MainWindow's storage access has) and reconnecting its
    # rename/delete signals, same as it already does from CardDialog's
    # own "Manage Types..." entry.
    manageCardTypesRequested = Signal()

    def __init__(self, parent=None, current_theme="macos_light",
                 confirm_deletes=True, card_numbering=True,
                 reduced_motion=False, large_text=False, focus_outlines=True,
                 remember_last_project=True, double_click_opens_card=True,
                 larger_click_targets=False, always_show_drop_zones=False,
                 uppercase_card_text=True, ui_scale=100,
                 diagnostics=None, ui_font="SF Pro Text", reader_font_size=12):
        super().__init__(parent)
        self.setWindowTitle("\u2699\uFE0F Settings")
        self.setMinimumWidth(480)
        self.selected_theme = current_theme

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        tabs = QTabWidget()
        # All tabs stay visible and reachable at any dialog width: tab
        # labels elide (truncate with "...") and the tab bar itself
        # shrinks with the dialog, instead of Qt's default behavior of
        # keeping every tab at full width and hiding the overflow behind
        # scroll arrows (which could leave a tab, e.g. "What's New",
        # scrolled out of view entirely when the dialog is narrow).
        tabs.setUsesScrollButtons(False)
        tabs.tabBar().setElideMode(Qt.ElideRight)
        tabs.tabBar().setExpanding(True)
        tabs.tabBar().setCursor(Qt.PointingHandCursor)
        outer.addWidget(tabs)
        self._tabs = tabs
        # Qt's QTabWidget sizes its stacked page area to fit the TALLEST
        # tab's content (the Themes grid, in this app), then holds every
        # other tab -- General, Accessibility, etc. -- at that same fixed
        # height. A short tab's own content (a few checkboxes) then sits
        # at the top with a large empty gap below it, since the
        # addStretch() at the end of each tab's layout was only ever
        # pushing content up within a page that's taller than it needs to
        # be, not shrinking the page itself. Reacting to currentChanged by
        # giving only the visible page an active size policy (every other
        # page's size no longer counts toward the stack's own sizeHint)
        # and re-fitting the dialog lets each tab claim only the height it
        # actually needs, removing that dead space.
        tabs.currentChanged.connect(self._on_settings_tab_changed)

        # --- Basic settings tab ---
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        basic_layout.setContentsMargins(16, 16, 16, 16)
        basic_layout.setSpacing(14)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("🔤 App font"))
        self.ui_font_combo = QFontComboBox()
        self.ui_font_combo.setAccessibleName("App font")
        # SF Pro remains the preferred family; Qt falls back if unavailable.
        self.ui_font_combo.setEditable(True)
        self.ui_font_combo.setCurrentText(ui_font)
        font_row.addWidget(self.ui_font_combo, 1)
        basic_layout.addLayout(font_row)
        font_hint = QLabel("SF Pro is used when installed. Otherwise, your system font is used.")
        font_hint.setWordWrap(True)
        basic_layout.addWidget(font_hint)
        reader_row = QHBoxLayout()
        reader_row.addWidget(QLabel("📖 Description text size"))
        self.reader_font_size_spin = QSpinBox()
        self.reader_font_size_spin.setRange(8, 32)
        self.reader_font_size_spin.setSuffix(" pt")
        self.reader_font_size_spin.setValue(reader_font_size)
        self.reader_font_size_spin.setAccessibleName("Description text size")
        reader_row.addWidget(self.reader_font_size_spin)
        basic_layout.addLayout(reader_row)

        self.confirm_deletes_check = QCheckBox("Ask for confirmation before deleting cards or columns")
        self.confirm_deletes_check.setChecked(confirm_deletes)
        basic_layout.addWidget(self.confirm_deletes_check)

        self.card_numbering_check = QCheckBox("Show card numbers within each column")
        self.card_numbering_check.setChecked(card_numbering)
        basic_layout.addWidget(self.card_numbering_check)

        self.remember_last_project_check = QCheckBox("Reopen the last active project on launch")
        self.remember_last_project_check.setChecked(remember_last_project)
        basic_layout.addWidget(self.remember_last_project_check)

        self.double_click_opens_card_check = QCheckBox("Double-click a card to open it for editing")
        self.double_click_opens_card_check.setChecked(double_click_opens_card)
        basic_layout.addWidget(self.double_click_opens_card_check)

        self.uppercase_card_text_check = QCheckBox("Show card text in ALL CAPS")
        self.uppercase_card_text_check.setChecked(uppercase_card_text)
        self.uppercase_card_text_check.setToolTip(
            "Display-only: titles and plain-text descriptions render in upper "
            "case, but the text you typed is kept exactly as-is and still "
            "edits normally."
        )
        basic_layout.addWidget(self.uppercase_card_text_check)

        # Rename/delete for custom card types used to be reachable only
        # via the "Manage Types..." entry buried at the bottom of the
        # Type dropdown inside the Add/Edit Card dialog -- meaning it
        # could only be found by first opening a card. A direct button
        # here in Settings (the conventional place to look for any
        # "manage X" action) opens the exact same ManageCardTypesDialog
        # without that detour. See manageCardTypesRequested below.
        manage_types_row = QHBoxLayout()
        manage_types_label = QLabel("Card types (rename, delete, or add new ones)")
        manage_types_label.setWordWrap(True)
        manage_types_row.addWidget(manage_types_label, 1)
        self.manage_types_btn = QPushButton("Manage\u2026")
        self.manage_types_btn.setCursor(Qt.PointingHandCursor)
        self.manage_types_btn.clicked.connect(self.manageCardTypesRequested.emit)
        manage_types_row.addWidget(self.manage_types_btn)
        basic_layout.addLayout(manage_types_row)

        basic_layout.addStretch()
        tabs.addTab(basic_tab, "\u2699\uFE0F General")

        # --- Accessibility tab ---
        access_tab = QWidget()
        access_layout = QVBoxLayout(access_tab)
        access_layout.setContentsMargins(16, 16, 16, 16)
        access_layout.setSpacing(14)

        self.large_text_check = QCheckBox("Larger text throughout the app")
        self.large_text_check.setChecked(large_text)
        access_layout.addWidget(self.large_text_check)

        # UI scale: an adjustable zoom on top of "Larger text" above,
        # rather than a replacement for it -- "Larger text" stays a quick
        # one-click bump, this is for dialing in a specific size (e.g.
        # for a high-DPI display or a projector). Both apply together:
        # this percentage scales whatever base size "Larger text" already
        # produced (see MainWindow._apply_theme), so turning this back to
        # 100% always returns to exactly "Larger text"'s own effect, on
        # or off, with no separate "reset" needed.
        scale_row = QHBoxLayout()
        scale_row.setSpacing(8)
        scale_label = QLabel("UI scale / zoom")
        scale_row.addWidget(scale_label)
        self.ui_scale_spin = QSpinBox()
        self.ui_scale_spin.setRange(80, 150)
        self.ui_scale_spin.setSingleStep(10)
        self.ui_scale_spin.setSuffix("%")
        self.ui_scale_spin.setValue(int(ui_scale) if ui_scale else 100)
        self.ui_scale_spin.setCursor(Qt.PointingHandCursor)
        scale_row.addWidget(self.ui_scale_spin)
        scale_row.addStretch()
        access_layout.addLayout(scale_row)

        self.reduced_motion_check = QCheckBox("Reduce motion (disable smooth scrolling animation)")
        self.reduced_motion_check.setChecked(reduced_motion)
        access_layout.addWidget(self.reduced_motion_check)

        self.focus_outlines_check = QCheckBox("Show a visible focus outline on the selected control")
        self.focus_outlines_check.setChecked(focus_outlines)
        access_layout.addWidget(self.focus_outlines_check)

        self.larger_click_targets_check = QCheckBox("Larger click/touch targets for buttons and checkboxes")
        self.larger_click_targets_check.setChecked(larger_click_targets)
        access_layout.addWidget(self.larger_click_targets_check)

        self.always_show_drop_zones_check = QCheckBox("Always show column drop-zone outlines (not just while dragging)")
        self.always_show_drop_zones_check.setChecked(always_show_drop_zones)
        access_layout.addWidget(self.always_show_drop_zones_check)

        hc_hint = QLabel("Tip: the \u201cHigh Contrast\u201d theme (Themes tab) pairs well with the options above.")
        hc_hint.setWordWrap(True)
        hc_hint.setStyleSheet("font-size: 11px;")
        access_layout.addWidget(hc_hint)

        access_layout.addStretch()
        tabs.addTab(access_tab, "\u267F Accessibility")

        # --- Themes tab ---
        themes_tab = QWidget()
        themes_outer = QVBoxLayout(themes_tab)
        themes_outer.setContentsMargins(16, 16, 16, 16)

        themes_scroll = QScrollArea()
        themes_scroll.setWidgetResizable(True)
        themes_scroll.setFrameShape(QFrame.NoFrame)
        themes_grid_host = QWidget()
        grid = QGridLayout(themes_grid_host)
        grid.setSpacing(10)

        self._swatches = {}
        for i, (theme_id, label) in enumerate(styles.theme_labels()):
            swatch = ThemeSwatch(theme_id, label, selected=(theme_id == current_theme))
            swatch.mousePressEvent = lambda e, tid=theme_id, sw=swatch: self._on_swatch_pressed(sw, tid)
            swatch.keyPressEvent = lambda e, tid=theme_id: self._on_swatch_key(e, tid)
            grid.addWidget(swatch, i // 4, i % 4)
            self._swatches[theme_id] = swatch

        themes_scroll.setWidget(themes_grid_host)
        themes_outer.addWidget(themes_scroll)
        tabs.addTab(themes_tab, "\U0001F3A8 Themes")

        # --- Changelog tab (version-scoped, paginated, category-grouped) ---
        changelog_tab = QWidget()
        changelog_outer = QVBoxLayout(changelog_tab)
        changelog_outer.setContentsMargins(16, 16, 16, 16)
        changelog_outer.setSpacing(10)

        version_label = QLabel(f"WhiteBoard v{app_meta.APP_VERSION}")
        version_label.setStyleSheet("font-weight: 700; font-size: 14px;")
        changelog_outer.addWidget(version_label)

        # app_meta.CHANGELOG stays in chronological/append order (oldest
        # release first) since that's the natural order to add new
        # releases to; this only reverses it for *display* so the
        # version picker's first entry -- and the page that opens by
        # default -- is the current release, not the oldest one.
        self._changelog_versions = list(reversed(app_meta.CHANGELOG))  # [(version, date, changes), ...]
        # Remembers each version's own current page across dropdown
        # switches (version_id -> page index), so paging into "1.0" page 3
        # and then checking "1.5" and coming back to "1.0" lands back on
        # page 3 instead of resetting to page 1 every time.
        self._changelog_page_by_version = {}
        self._changelog_page_size = 10

        version_row = QHBoxLayout()
        version_row.addWidget(QLabel("Version"))
        self._changelog_version_combo = FitPopupComboBox()
        # Populated before connecting currentIndexChanged (below), not
        # after: addItem() on the first item fires currentIndexChanged
        # itself (index moves -1 -> 0), and connecting first would call
        # _on_changelog_version_changed -> _render_changelog_page() before
        # _changelog_scroll/_changelog_prev_btn/_changelog_next_btn exist
        # yet (they're built further down), raising AttributeError.
        for version, date, _changes in self._changelog_versions:
            self._changelog_version_combo.addItem(f"v{version} \u2014 {date}", version)
        version_row.addWidget(self._changelog_version_combo, 1)
        changelog_outer.addLayout(version_row)

        self._changelog_scroll = QScrollArea()
        self._changelog_scroll.setWidgetResizable(True)
        self._changelog_scroll.setFrameShape(QFrame.NoFrame)
        changelog_outer.addWidget(self._changelog_scroll, 1)

        nav_row = QHBoxLayout()
        self._changelog_prev_btn = QToolButton()
        self._changelog_prev_btn.setText("\u2190 Prev")
        self._changelog_prev_btn.setCursor(Qt.PointingHandCursor)
        self._changelog_prev_btn.clicked.connect(self._on_changelog_prev)
        nav_row.addWidget(self._changelog_prev_btn)

        self._changelog_page_label = QLabel("")
        self._changelog_page_label.setAlignment(Qt.AlignCenter)
        nav_row.addWidget(self._changelog_page_label, 1)

        self._changelog_next_btn = QToolButton()
        self._changelog_next_btn.setText("Next \u2192")
        self._changelog_next_btn.setCursor(Qt.PointingHandCursor)
        self._changelog_next_btn.clicked.connect(self._on_changelog_next)
        nav_row.addWidget(self._changelog_next_btn)

        changelog_outer.addLayout(nav_row)
        tabs.addTab(changelog_tab, "\U0001F195 What's New")
        # Connect only now that every widget _render_changelog_page()
        # touches (_changelog_scroll, _changelog_prev_btn/_next_btn)
        # actually exists, then render explicitly -- the combo's current
        # index is already 0 (the newest version, since the list was
        # reversed above) from the addItem() loop, so this doesn't need
        # to change the index to trigger the first render.
        self._changelog_version_combo.currentIndexChanged.connect(self._on_changelog_version_changed)
        self._render_changelog_page()

        # --- Diagnostics tab ---
        diag_tab = QWidget()
        diag_outer = QVBoxLayout(diag_tab)
        diag_outer.setContentsMargins(16, 16, 16, 16)
        diag_outer.setSpacing(10)

        self._diag_labels = {}
        for key, caption in [
            ("version", "App version"),
            ("file_size", "Data file size"),
            ("columns", "Columns (this project)"),
            ("cards", "Cards (this project)"),
        ]:
            row = QHBoxLayout()
            cap = QLabel(caption)
            cap.setStyleSheet("font-weight: 600;")
            row.addWidget(cap)
            row.addStretch()
            val = QLabel("\u2014")
            row.addWidget(val)
            diag_outer.addLayout(row)
            self._diag_labels[key] = val

        diag_outer.addSpacing(8)

        reset_hint = QLabel(
            "Clearing removes every column and card in the current "
            "project so you can start over with a blank board. Undo "
            "restores exactly what was just removed, until you close "
            "Settings or clear again."
        )
        reset_hint.setWordWrap(True)
        reset_hint.setStyleSheet("font-size: 11px;")
        diag_outer.addWidget(reset_hint)

        reset_row = QHBoxLayout()
        self._clear_board_btn = QPushButton("\U0001F9F9 Clear Board")
        self._clear_board_btn.setObjectName("DangerButton")
        self._clear_board_btn.setToolTip(
            "Remove every column and card in the current project"
        )
        self._clear_board_btn.setCursor(Qt.PointingHandCursor)
        self._clear_board_btn.clicked.connect(self._on_clear_board_clicked)
        reset_row.addWidget(self._clear_board_btn)

        self._undo_clear_btn = QPushButton("\u21A9\uFE0F Undo")
        self._undo_clear_btn.setToolTip("Restore what Clear Board just removed")
        self._undo_clear_btn.setEnabled(False)
        self._undo_clear_btn.setCursor(Qt.PointingHandCursor)
        self._undo_clear_btn.clicked.connect(self._on_undo_clear_clicked)
        reset_row.addWidget(self._undo_clear_btn)

        reset_row.addStretch()
        diag_outer.addLayout(reset_row)

        diag_outer.addSpacing(12)

        # Recent errors: a lightweight, read-only view into error_log.py's
        # in-memory buffer -- separate from the Clear Board undo above,
        # this just surfaces whatever save/open/import/export failures (or
        # unhandled exceptions) have occurred this session, so a person
        # hitting a problem has somewhere to look/copy from without
        # digging through the on-disk error.log by hand.
        log_header_row = QHBoxLayout()
        log_cap = QLabel("Recent errors")
        log_cap.setStyleSheet("font-weight: 600;")
        log_header_row.addWidget(log_cap)
        log_header_row.addStretch()
        self._clear_log_btn = QPushButton("\U0001F9F9 Clear Log")
        self._clear_log_btn.setToolTip("Clear the recent-errors list")
        self._clear_log_btn.setCursor(Qt.PointingHandCursor)
        self._clear_log_btn.clicked.connect(self._on_clear_log_clicked)
        log_header_row.addWidget(self._clear_log_btn)
        diag_outer.addLayout(log_header_row)

        self._error_log_view = QTextEdit()
        self._error_log_view.setObjectName("ErrorLogView")
        self._error_log_view.setReadOnly(True)
        self._error_log_view.setFixedHeight(120)
        self._error_log_view.setPlaceholderText("No errors recorded this session.")
        diag_outer.addWidget(self._error_log_view)

        diag_outer.addStretch()
        tabs.addTab(diag_tab, "\U0001FA7A Diagnostics")
        self.refresh_diagnostics(diagnostics)

        # Now that every tab exists, apply the size-policy pass once for
        # the initially-selected tab (General), so the dialog opens
        # already fitted to it instead of at the tallest tab's height.
        self._on_settings_tab_changed(tabs.currentIndex())

        button_row = QHBoxLayout()
        button_row.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        _apply_pointer_cursor(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        button_row.addWidget(buttons)
        outer.addLayout(button_row)

    # Leading-emoji -> category label, used to group each version's notes
    # (see _categorize_change). Every changelog line in app_meta.py starts
    # with one of these markers (matching the emoji-forward tone used
    # throughout the app's buttons/tooltips/menus), so this covers the
    # full existing history without needing a separate category field per
    # entry. Anything that doesn't match falls into "Other" rather than
    # being dropped.
    _CHANGELOG_CATEGORIES = [
        ("\U0001F41B", "\U0001F41B Bug Fixes"),
        ("\u26A1", "\u26A1 Performance"),
        ("\u267F", "\u267F Accessibility"),
        ("\U0001F6E0\uFE0F", "\U0001F6E0\uFE0F Build & Packaging"),
        ("\U0001F6D1", "\U0001F6E0\uFE0F Build & Packaging"),
        ("\u231B", "\U0001F6E0\uFE0F Build & Packaging"),
        ("\u2611\uFE0F", "\u2699\uFE0F Features"),
        ("\U0001F5D1\uFE0F", "\u2699\uFE0F Features"),
        ("\U0001F5B1\uFE0F", "\u2699\uFE0F Features"),
        ("\U0001F4CE", "\u2699\uFE0F Features"),
        ("\U0001F52C", "\u2699\uFE0F Features"),
        ("\u2699\uFE0F", "\u2699\uFE0F Features"),
        ("\U0001F3F7\uFE0F", "\u2699\uFE0F Features"),
        ("\U0001F3A8", "\U0001F5A5\uFE0F UI & Design"),
        ("\U0001F5A5\uFE0F", "\U0001F5A5\uFE0F UI & Design"),
        ("\U0001F308", "\U0001F5A5\uFE0F UI & Design"),
        ("\u2795", "\u2699\uFE0F Features"),
        ("\U0001F4CB", "\u2699\uFE0F Features"),
        ("\U0001F4C2", "\u2699\uFE0F Features"),
        ("\U0001F4D6", "\u2699\uFE0F Features"),
        ("\U0001F4DC", "\u2699\uFE0F Features"),
        ("\U0001F521", "\u2699\uFE0F Features"),
        ("\U0001F522", "\u2699\uFE0F Features"),
        ("\U0001F4CF", "\U0001F5A5\uFE0F UI & Design"),
        ("\u2728", "\U0001F5A5\uFE0F UI & Design"),
        ("\U0001F5C2\uFE0F", "\u2699\uFE0F Features"),
        ("\U0001F58B\uFE0F", "\u2699\uFE0F Features"),
        ("\U0001F600", "\U0001F5A5\uFE0F UI & Design"),
        ("\U0001F4AC", "\U0001F5A5\uFE0F UI & Design"),
        ("\U0001F6E1\uFE0F", "\U0001F6E0\uFE0F Build & Packaging"),
        ("\u270F\uFE0F", "\U0001F5A5\uFE0F UI & Design"),
        ("\U0001F680", "\u2699\uFE0F Features"),
        ("\U0001F527", "\U0001F41B Bug Fixes"),
        ("\U0001F9F9", "\U0001F6E0\uFE0F Build & Packaging"),
        ("\U0001F6A9", "\u2699\uFE0F Features"),
        ("\U0001F5BC\uFE0F", "\u2699\uFE0F Features"),
        ("\u21A9\uFE0F", "\u2699\uFE0F Features"),
        ("\U0001F514", "\u2699\uFE0F Features"),
        ("\u26A0\uFE0F", "\u2699\uFE0F Features"),
    ]

    @classmethod
    def _categorize_change(cls, change: str) -> str:
        for marker, category in cls._CHANGELOG_CATEGORIES:
            if change.startswith(marker):
                return category
        return "\U0001F4CC Other"

    # Fixed display order for the grouped sections, independent of the
    # order categories happen to first appear in a given version's list --
    # otherwise which category renders first would shuffle from version
    # to version based on whatever the first item's emoji happened to be.
    _CATEGORY_ORDER = [
        "\U0001F41B Bug Fixes",
        "\u26A1 Performance",
        "\u2699\uFE0F Features",
        "\U0001F5A5\uFE0F UI & Design",
        "\u267F Accessibility",
        "\U0001F6E0\uFE0F Build & Packaging",
        "\U0001F4CC Other",
    ]

    def _on_changelog_version_changed(self, index):
        if index < 0:
            return
        self._render_changelog_page()

    def _current_changelog_entry(self):
        """(version, date, changes) for whatever version is currently
        selected in the dropdown, or None if the list is somehow empty
        (not a reachable state today, since app_meta.CHANGELOG always has
        at least one entry, but this keeps rendering a no-op rather than
        raising if that ever changed)."""
        index = self._changelog_version_combo.currentIndex()
        if index < 0 or index >= len(self._changelog_versions):
            return None
        return self._changelog_versions[index]

    def _render_changelog_page(self):
        """Render only the current page of the *currently selected
        version's* changelog items, grouped by category, instead of
        building every QLabel for the whole history up front -- keeps the
        tab construction cheap and gives a shorter, browsable list instead
        of one long scrolling page. Each version keeps its own page
        position (see _changelog_page_by_version) so switching versions in
        the dropdown and switching back doesn't reset paging progress."""
        entry = self._current_changelog_entry()
        if entry is None:
            return
        version, date, changes = entry

        # Group first (stable order: category order first, original
        # within-category order preserved), then paginate the flattened,
        # grouped sequence -- so a page boundary never splits oddly and
        # every page still reads top-to-bottom by category.
        by_category = {}
        for change in changes:
            by_category.setdefault(self._categorize_change(change), []).append(change)
        grouped_items = []  # list of (category_or_None, change)
        for category in self._CATEGORY_ORDER:
            for i, change in enumerate(by_category.get(category, [])):
                grouped_items.append((category if i == 0 else None, change))

        total = len(grouped_items)
        page_count = max(1, (total + self._changelog_page_size - 1) // self._changelog_page_size)
        page = self._changelog_page_by_version.get(version, 0)
        page = max(0, min(page, page_count - 1))
        self._changelog_page_by_version[version] = page

        start = page * self._changelog_page_size
        end = min(start + self._changelog_page_size, total)
        page_items = grouped_items[start:end]

        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        v_label = QLabel(f"v{version}")
        v_label.setObjectName("ChangelogVersion")
        header_row.addWidget(v_label)
        d_label = QLabel(date)
        d_label.setObjectName("ChangelogDate")
        header_row.addWidget(d_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        for category, change in page_items:
            if category is not None:
                cat_label = QLabel(category)
                cat_label.setObjectName("ChangelogCategory")
                layout.addWidget(cat_label)
            item = QLabel(f"\u2022 {change}")
            item.setWordWrap(True)
            layout.addWidget(item)

        layout.addStretch()
        # setWidget() on a QScrollArea deletes the previous widget it owned,
        # so the prior page's QLabels are cleaned up automatically here --
        # no manual teardown needed between pages.
        self._changelog_scroll.setWidget(host)
        self._changelog_scroll.verticalScrollBar().setValue(0)

        self._changelog_page_label.setText(f"Page {page + 1} of {page_count}")
        self._changelog_prev_btn.setEnabled(page > 0)
        self._changelog_next_btn.setEnabled(page < page_count - 1)

    def _on_changelog_prev(self):
        entry = self._current_changelog_entry()
        if entry is None:
            return
        version = entry[0]
        page = self._changelog_page_by_version.get(version, 0)
        if page > 0:
            self._changelog_page_by_version[version] = page - 1
            self._render_changelog_page()

    def _on_changelog_next(self):
        entry = self._current_changelog_entry()
        if entry is None:
            return
        version, _date, changes = entry
        by_category = {}
        for change in changes:
            by_category.setdefault(self._categorize_change(change), []).append(change)
        total = sum(len(v) for v in by_category.values())
        page_count = max(1, (total + self._changelog_page_size - 1) // self._changelog_page_size)
        page = self._changelog_page_by_version.get(version, 0)
        if page < page_count - 1:
            self._changelog_page_by_version[version] = page + 1
            self._render_changelog_page()

    def _on_settings_tab_changed(self, index):
        """Give only the current tab page an active size policy so the
        QTabWidget's stacked area sizes to *that* page's own content
        instead of the tallest page among all of them -- see the
        currentChanged connection above for why. Ignored pages report a
        (0, 0) sizeHint to the stack, so they stop influencing its height
        entirely; they still render normally once selected again, since
        this only touches sizing, not visibility or content."""
        tabs = getattr(self, "_tabs", None)
        if tabs is None:
            return
        for i in range(tabs.count()):
            page = tabs.widget(i)
            if page is None:
                continue
            if i == index:
                page.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            else:
                page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        tabs.updateGeometry()
        # Defer the actual resize by one event-loop turn: updateGeometry()
        # only invalidates the cached size hints, it doesn't recompute the
        # layout synchronously, so calling adjustSize() in this same call
        # would still measure against the stale (pre-change) hint.
        QTimer.singleShot(0, self.adjustSize)

    def _on_swatch_pressed(self, swatch, theme_id):
        swatch.setFocus(Qt.MouseFocusReason)
        self._on_theme_clicked(theme_id)

    def _on_swatch_key(self, event, theme_id):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._on_theme_clicked(theme_id)
        else:
            event.ignore()

    def _on_theme_clicked(self, theme_id):
        self.selected_theme = theme_id
        for tid, swatch in self._swatches.items():
            swatch.setProperty("selected", tid == theme_id)
            swatch.style().unpolish(swatch)
            swatch.style().polish(swatch)
        # Live-preview the theme immediately: picking a swatch shows its
        # effect right away without closing the dialog. The dialog itself
        # stays open either way -- only OK/Cancel close it.
        self.themeApplied.emit(theme_id)

    def get_values(self):
        return {
            "theme": self.selected_theme,
            "ui_font": self.ui_font_combo.currentText().strip() or "SF Pro Text",
            "reader_font_size": self.reader_font_size_spin.value(),
            "confirm_deletes": self.confirm_deletes_check.isChecked(),
            "card_numbering": self.card_numbering_check.isChecked(),
            "large_text": self.large_text_check.isChecked(),
            "ui_scale": self.ui_scale_spin.value(),
            "reduced_motion": self.reduced_motion_check.isChecked(),
            "focus_outlines": self.focus_outlines_check.isChecked(),
            "remember_last_project": self.remember_last_project_check.isChecked(),
            "double_click_opens_card": self.double_click_opens_card_check.isChecked(),
            "uppercase_card_text": self.uppercase_card_text_check.isChecked(),
            "larger_click_targets": self.larger_click_targets_check.isChecked(),
            "always_show_drop_zones": self.always_show_drop_zones_check.isChecked(),
        }

    # ---------------------------------------------------------- diagnostics
    def refresh_diagnostics(self, diagnostics: dict = None):
        """Update the Diagnostics tab's numbers and Undo availability.
        diagnostics: {"version", "file_size_bytes", "columns", "cards",
        "can_undo"}. Called once at construction and again by MainWindow
        right after a Clear/Undo (or a log clear) so the tab reflects the
        new state without the dialog needing to be closed and reopened."""
        d = diagnostics or {}
        self._diag_labels["version"].setText(f"v{d.get('version', app_meta.APP_VERSION)}")
        size = d.get("file_size_bytes", 0)
        if size >= 1024 * 1024:
            size_text = f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            size_text = f"{size / 1024:.1f} KB"
        else:
            size_text = f"{size} bytes"
        self._diag_labels["file_size"].setText(size_text)
        self._diag_labels["columns"].setText(str(d.get("columns", 0)))
        self._diag_labels["cards"].setText(str(d.get("cards", 0)))
        self._undo_clear_btn.setEnabled(bool(d.get("can_undo", False)))
        # Recent errors: read directly from error_log's in-memory buffer
        # rather than through the diagnostics dict, same as the theme
        # swatches read directly from styles.py -- this is read-only
        # session state, not part of the small board-summary payload
        # MainWindow otherwise assembles here.
        entries = error_log.recent_entries()
        self._error_log_view.setPlainText("\n\n".join(entries) if entries else "")
        self._clear_log_btn.setEnabled(bool(entries))

    def _on_clear_log_clicked(self):
        self.clearErrorLogRequested.emit()

    def _on_clear_board_clicked(self):
        confirm = QMessageBox.question(
            self, "\U0001F9F9 Clear Board",
            "Remove every column and card in the current project?\n"
            "You can undo this from here until Settings is closed.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.clearBoardRequested.emit()

    def _on_undo_clear_clicked(self):
        self.revertBoardRequested.emit()


class NewCardTypeDialog(QDialog):
    """Prompt for a new custom card type name."""

    def __init__(self, parent=None, existing_types=None):
        super().__init__(parent)
        self.existing_types = existing_types or []
        self.setWindowTitle("\u2795 New Card Type")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel("Type name"))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("e.g. Research, Bug, Question")
        layout.addWidget(self.edit)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #E0393E; font-size: 11px;")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        _apply_pointer_cursor(buttons)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.edit.setFocus()

    def _on_accept(self):
        name = self.edit.text().strip()
        if not name:
            self.edit.setStyleSheet("border: 1px solid #E0393E;")
            return
        if name in self.existing_types:
            self.error_label.setText("\u26A0\uFE0F That type already exists.")
            self.error_label.show()
            return
        self.accept()

    def get_value(self) -> str:
        return self.edit.text().strip()
