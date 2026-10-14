"""📊 Show sortable card rows without changing board order."""
import time
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from card_tools import due_text, search_text, matches_card, plain_tooltip
from models import priority_label, PRIORITY_LEVELS


class CardTableModel(QAbstractTableModel):
    headers = ['Title', 'Column', 'Type', 'Priority', 'Due', 'Labels', 'Files']
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.cards = []
        self.columns = {}
        self.text_index = {}

    def set_project(self, project):
        self.beginResetModel()
        self.project = project
        self.cards = list(project.cards) if project else []
        self.columns = {c.id: c.name for c in project.columns} if project else {}
        self.text_index = {c.id: search_text(project, c) for c in self.cards}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.cards)
    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        card = self.cards[index.row()]
        if role == Qt.UserRole:
            return card.id
        if role == Qt.UserRole + 1:
            if index.column() == 4:
                return card.due_at if card.due_at is not None else float('inf')
            if index.column() == 3:
                return PRIORITY_LEVELS.index(card.priority) if card.priority in PRIORITY_LEVELS else 4
            if index.column() == 6:
                return len(card.attachments)
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            value = [card.title, self.columns.get(card.column_id, ''), card.card_type,
                    priority_label(card.priority), due_text(card.due_at, time.time()),
                    ', '.join(card.labels), str(len(card.attachments)) if card.attachments else ''][index.column()]
            return plain_tooltip(value) if role == Qt.ToolTipRole else value
        return None


class CardFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filters = {}
        self.setSortCaseSensitivity(Qt.CaseInsensitive)
    def set_filters(self, filters):
        self.beginFilterChange()
        self.filters = dict(filters)
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        card = model.cards[row]
        filters = dict(self.filters)
        query = filters.pop('query', '').casefold().split()
        if query and not all(word in model.text_index[card.id] for word in query):
            return False
        return matches_card(model.project, card, filters, time.time())
    def lessThan(self, left, right):
        if left.column() in (3, 4, 6):
            return self.sourceModel().data(left, Qt.UserRole + 1) < self.sourceModel().data(right, Qt.UserRole + 1)
        return super().lessThan(left, right)
