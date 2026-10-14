"""🧮 Filter projects and switch between board and list views."""
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QLineEdit, QPushButton, QComboBox, QStackedWidget, QTableView, QHeaderView, QLabel, QInputDialog, QMessageBox, QMenu
from card_table import CardTableModel, CardFilterProxy
from card_tools import matches_card
from models import PRIORITY_LEVELS, priority_label
from view_state import clean_filters, capture_view, apply_view


class WorkspacePanel(QWidget):
    def __init__(self, window, board):
        super().__init__(window)
        self.window = window
        self.project = None
        self.loading = False
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        controls = QWidget(); rows = QVBoxLayout(controls); rows.setContentsMargins(8, 4, 8, 4)
        first = QHBoxLayout(); rows.addLayout(first)
        self.query = QLineEdit(); self.query.setPlaceholderText('Filter this project…'); self.query.setAccessibleName('Filter this project')
        self.query.setClearButtonEnabled(True); self.query.setMinimumWidth(150); self.query.setMaximumWidth(250); first.addWidget(self.query)
        search = QPushButton('🔎 All projects'); search.clicked.connect(window._open_search); first.addWidget(search)
        palette = QPushButton('🧭 Commands'); palette.clicked.connect(window._open_palette); first.addWidget(palette)
        self.mode = QComboBox(); self.mode.addItem('🧱 Board', 'board'); self.mode.addItem('📋 List', 'list'); self.mode.setAccessibleName('Board or list view'); first.addWidget(self.mode); first.addStretch()
        second = QHBoxLayout(); rows.addLayout(second)
        self.type_combo = QComboBox(); self.type_combo.setAccessibleName('Filter by type'); second.addWidget(self.type_combo)
        self.priority_combo = QComboBox(); self.priority_combo.addItem('Any priority', ''); self.priority_combo.addItem('No priority', 'none')
        for key in PRIORITY_LEVELS: self.priority_combo.addItem(priority_label(key), key)
        self.priority_combo.setAccessibleName('Filter by priority'); second.addWidget(self.priority_combo)
        self.label_combo = QComboBox(); self.label_combo.setAccessibleName('Filter by label'); second.addWidget(self.label_combo)
        self.due_combo = QComboBox()
        for text, key in [('Any due date', ''), ('Overdue', 'overdue'), ('Due today', 'today'), ('No due date', 'undated')]: self.due_combo.addItem(text, key)
        self.due_combo.setAccessibleName('Filter by due date'); second.addWidget(self.due_combo)
        self.views = QComboBox(); self.views.setAccessibleName('Saved views'); second.addWidget(self.views)
        save = QPushButton('💾 Save view'); save.clicked.connect(self.save_view); second.addWidget(save)
        remove = QPushButton('Remove view'); remove.clicked.connect(self.delete_view); second.addWidget(remove)
        reset = QPushButton('↔️ Auto widths'); reset.clicked.connect(self.reset_widths); second.addWidget(reset)
        clear = QPushButton('Clear filters'); clear.clicked.connect(self.clear_filters); second.addWidget(clear)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); scroll.setWidget(controls); scroll.setFixedHeight(118)
        self.controls = controls
        self.control_scroll = scroll
        self.fit_toolbar()
        root.addWidget(scroll)
        self.stack = QStackedWidget(); self.stack.addWidget(board)
        self.table = QTableView(); self.model = CardTableModel(self); self.proxy = CardFilterProxy(self); self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy); self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows); self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers); self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setAccessibleName('Project task list')
        self.table.doubleClicked.connect(self.edit_row); self.table.activated.connect(self.edit_row)
        self.table.selectionModel().selectionChanged.connect(self._list_selection)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._sort_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu); self.table.customContextMenuRequested.connect(self._list_menu)
        self.stack.addWidget(self.table); root.addWidget(self.stack, 1)
        self.summary = QLabel(); self.summary.setTextFormat(Qt.PlainText); root.addWidget(self.summary)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(180); self.timer.timeout.connect(self.apply_filters)
        self.query.textChanged.connect(self._changed)
        for combo in (self.type_combo, self.priority_combo, self.label_combo, self.due_combo): combo.currentIndexChanged.connect(self._changed)
        self.mode.currentIndexChanged.connect(self._mode_changed); self.views.activated.connect(self.restore_view)
    def fit_toolbar(self):
        self.controls.ensurePolished()
        height = self.controls.sizeHint().height() + self.control_scroll.horizontalScrollBar().sizeHint().height() + 6
        self.control_scroll.setFixedHeight(max(110, height))

    def _changed(self, *args):
        if not self.loading:
            self.timer.start()
    def _select_data(self, combo, value):
        index = combo.findData(value)
        if index < 0 and value:
            combo.addItem(str(value), value); index = combo.count() - 1
        combo.setCurrentIndex(max(0, index))
    def set_project(self, project):
        self.timer.stop(); self.project = project; self.loading = True
        state = clean_filters(project.view_filters) if project else {}
        self.query.setText(state.get('query', ''))
        self.type_combo.clear(); self.type_combo.addItem('Any type', '')
        types = self.window._available_card_types()
        if project:
            types = list(dict.fromkeys(types + [c.card_type for c in project.cards]))
        for name in types: self.type_combo.addItem(name, name)
        self.label_combo.clear(); self.label_combo.addItem('Any label', '')
        labels = sorted({label for c in project.cards for label in c.labels}, key=str.casefold) if project else []
        for label in labels: self.label_combo.addItem(label, label)
        for key, combo in [('type', self.type_combo), ('priority', self.priority_combo), ('label', self.label_combo), ('due', self.due_combo)]: self._select_data(combo, state.get(key, ''))
        self._select_data(self.mode, project.view_mode if project else 'board')
        self.stack.setCurrentIndex(1 if project and project.view_mode == 'list' else 0)
        self.views.clear(); self.views.addItem('Saved views…', None)
        if project:
            for i, view in enumerate(project.saved_views): self.views.addItem(view['name'], i)
        self.loading = False; self.refresh()
    def filters(self):
        return {key: value for key, value in [('query', self.query.text().strip()), ('type', self.type_combo.currentData()), ('priority', self.priority_combo.currentData()), ('label', self.label_combo.currentData()), ('due', self.due_combo.currentData())] if value}
    def matches(self, card):
        return matches_card(self.project, card, self.project.view_filters, time.time()) if self.project else True
    def apply_filters(self):
        if not self.project:
            return
        self.project.view_filters = self.filters()
        self.window._selected_card_ids.clear(); self.window._selection_anchor = None
        self.window._refresh_all_columns()
        self.window._save(self.project.id)
    def clear_filters(self):
        if self.project:
            self.project.view_filters = {}; self.set_project(self.project); self.window._refresh_all_columns(); self.window._save(self.project.id)
    def _mode_changed(self, *args):
        if self.loading or not self.project:
            return
        self.project.view_mode = self.mode.currentData()
        self.stack.setCurrentIndex(1 if self.project.view_mode == 'list' else 0)
        self.window._clear_selection(); self.refresh(); self.window._save(self.project.id)
    def refresh(self):
        offset = self.table.verticalScrollBar().value()
        self.loading = True
        selected = set(self.window._selected_card_ids)
        label = self.label_combo.currentData()
        type_name = self.type_combo.currentData()
        self.label_combo.clear(); self.label_combo.addItem('Any label', '')
        self.type_combo.clear(); self.type_combo.addItem('Any type', '')
        if self.project:
            for name in sorted({v for c in self.project.cards for v in c.labels}, key=str.casefold):
                self.label_combo.addItem(name, name)
            for name in dict.fromkeys(self.window._available_card_types() + [c.card_type for c in self.project.cards]):
                self.type_combo.addItem(name, name)
        self._select_data(self.label_combo, label)
        self._select_data(self.type_combo, type_name)
        self.model.set_project(self.project)
        self.proxy.set_filters(self.project.view_filters if self.project else {})
        if self.project:
            col, descending = self.project.list_sort
            self.table.sortByColumn(col, Qt.DescendingOrder if descending else Qt.AscendingOrder)
            selection = self.table.selectionModel()
            from PySide6.QtCore import QItemSelectionModel
            for row in range(self.proxy.rowCount()):
                if self.proxy.index(row, 0).data(Qt.UserRole) in selected:
                    selection.select(self.proxy.index(row, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
            count = self.proxy.rowCount(); total = len(self.project.cards)
            self.summary.setText(f'{count} of {total} cards' if count else ('No cards match these filters. Clear filters to see the board.' if total else 'No cards yet. Add a card to get started.'))
        else:
            self.summary.setText('No project selected')
        self.table.doItemsLayout()
        self.table.verticalScrollBar().setValue(offset)
        self.loading = False
    def sync_selection(self):
        from PySide6.QtCore import QItemSelectionModel
        previous = self.loading
        self.loading = True
        selection = self.table.selectionModel()
        selection.clearSelection()
        selected = self.window._selected_card_ids
        for row in range(self.proxy.rowCount()):
            if self.proxy.index(row, 0).data(Qt.UserRole) in selected:
                selection.select(self.proxy.index(row, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self.loading = previous

    def update_clock(self):
        if self.model.cards:
            self.model.dataChanged.emit(self.model.index(0, 4), self.model.index(len(self.model.cards) - 1, 4), [Qt.DisplayRole])
        if self.project and self.project.view_filters.get('due'):
            self.proxy.set_filters(self.project.view_filters)
        for column in self.window._column_widgets.values():
            for widget in column._card_widgets.values():
                widget.refresh_metadata()

    def _sort_changed(self, column, order):
        if not self.loading and self.project:
            self.project.list_sort = [column, order == Qt.DescendingOrder]
            self.window._save(self.project.id)
    def _list_selection(self, *args):
        if not self.loading and self.project and self.project.view_mode == 'list':
            self.window._selected_card_ids = {index.data(Qt.UserRole) for index in self.table.selectionModel().selectedRows()}
            self.window._apply_selection_to_columns()
    def edit_row(self, index):
        if index.isValid(): self.window._on_edit_card(index.data(Qt.UserRole))
    def _list_menu(self, position):
        index = self.table.indexAt(position)
        if not index.isValid(): return
        identifier = index.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction('Edit', lambda: self.window._on_edit_card(identifier))
        menu.addAction('Duplicate', lambda: self.window._on_duplicate_card(identifier))
        menu.addAction('Delete', lambda: self.window._on_delete_card(identifier))
        menu.exec(self.table.viewport().mapToGlobal(position))
    def save_view(self):
        if not self.project: return
        self.timer.stop(); self.apply_filters()
        name, ok = QInputDialog.getText(self, '💾 Save view', 'View name:')
        name = name.strip()
        if not ok or not name: return
        view = capture_view(self.project, self.window._column_widgets, name)
        existing = next((i for i, v in enumerate(self.project.saved_views) if v['name'].casefold() == name.casefold()), None)
        if existing is not None:
            if QMessageBox.question(self, 'Replace saved view?', 'Replace the view with this name?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
            self.project.saved_views[existing] = view
        else:
            self.project.saved_views.append(view)
        self.window._save(self.project.id); self.set_project(self.project)
    def restore_view(self, index):
        selected = self.views.itemData(index)
        if selected is None or not self.project: return
        state = apply_view(self.project, self.project.saved_views[selected])
        self.window._column_sort_state.pop(self.project.id, None)
        self.window._load_active_project()
        for column_id, data in state['columns'].items():
            widget = self.window._column_widgets.get(column_id)
            if widget:
                widget._type_filter = data['type_filter']; widget._populate_filter_combo(); widget._render_filtered_cards()
        self.window._save(self.project.id)
    def delete_view(self):
        selected = self.views.currentData()
        if selected is None or not self.project: return
        if QMessageBox.question(self, 'Remove view?', 'Remove this saved view? Your cards will stay.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.project.saved_views.pop(selected); self.window._save(self.project.id); self.set_project(self.project)
    def reset_widths(self):
        if self.project:
            for column in self.project.columns: column.width = None
            self.window._apply_column_stretch_width(); self.window._save(self.project.id)
