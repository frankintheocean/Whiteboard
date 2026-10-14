"""🔎 Find cards, projects, and commands from the keyboard."""
from dataclasses import dataclass
from card_tools import plain_tooltip
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QTableView, QLabel, QDialogButtonBox, QHeaderView


@dataclass
class FindEntry:
    title: str
    detail: str
    search: str
    callback: object
    kind: str = 'card'


class FindModel(QAbstractTableModel):
    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.entries = entries
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)
    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2
    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role in (Qt.DisplayRole, Qt.ToolTipRole):
            entry = self.entries[index.row()]
            value = entry.title if index.column() == 0 else entry.detail
            return plain_tooltip(value) if role == Qt.ToolTipRole else value
        return None
    def headerData(self, column, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ['Result', 'Location / action'][column]
        return None


class FindProxy(QSortFilterProxyModel):
    def set_query(self, text):
        self.beginFilterChange()
        self.commands_only = text.startswith('>')
        self.words = text.lstrip('>').casefold().split()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
    def filterAcceptsRow(self, row, parent):
        entry = self.sourceModel().entries[row]
        if getattr(self, 'commands_only', False) and entry.kind != 'command':
            return False
        return all(word in entry.search for word in getattr(self, 'words', []))


class QuickFindDialog(QDialog):
    def __init__(self, entries, parent=None, palette=False):
        super().__init__(parent)
        self.setWindowTitle('🧭 Command palette' if palette else '🔎 Search all projects')
        self.resize(720, 500)
        self.selected_entry = None
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText('Search actions, projects, and cards. Use > for commands.' if palette else 'Search titles, notes, labels, types, or file names…')
        self.query.setAccessibleName('Search all projects and actions')
        layout.addWidget(self.query)
        self.model = FindModel(entries, self)
        self.proxy = FindProxy(self); self.proxy.setSourceModel(self.model)
        self.results = QTableView()
        self.results.setModel(self.proxy)
        self.results.setSelectionBehavior(QTableView.SelectRows)
        self.results.setSelectionMode(QTableView.SingleSelection)
        self.results.setEditTriggers(QTableView.NoEditTriggers)
        self.results.verticalHeader().hide()
        self.results.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.results.doubleClicked.connect(self._choose)
        self.query.returnPressed.connect(self._choose)
        self.results.activated.connect(self._choose)
        layout.addWidget(self.results, 1)
        self.count = QLabel(); layout.addWidget(self.count)
        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._choose); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.query.textChanged.connect(self._filter)
        self._filter(''); self.query.setFocus()
    def _filter(self, text):
        self.proxy.set_query(text)
        count = self.proxy.rowCount()
        self.count.setText(f'{count} result(s)' if count else 'No matches. Try fewer words.')
        if count:
            self.results.selectRow(0)
    def _choose(self, *args):
        index = self.results.currentIndex()
        if index.isValid():
            source = self.proxy.mapToSource(index)
            self.selected_entry = self.model.entries[source.row()]
            self.accept()
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Down, Qt.Key_Up) and self.query.hasFocus():
            count = self.proxy.rowCount()
            if count:
                row = self.results.currentIndex().row()
                self.results.selectRow(max(0, min(count - 1, row + (1 if event.key() == Qt.Key_Down else -1))))
            event.accept()
        else:
            super().keyPressEvent(event)
