"""↔️ Resize board columns with a drag handle."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget


class ColumnResizeHandle(QWidget):
    preview = Signal(int)
    committed = Signal(int)
    def __init__(self, column):
        super().__init__(column)
        self.column = column
        self.setCursor(Qt.SizeHorCursor)
        self.setToolTip('Drag to resize this column. Use its menu for an exact width.')
        self.setAccessibleName('Resize column')
        self.start_x = None
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_x = event.globalPosition().x()
            self.start_width = self.column.width()
            event.accept()
    def mouseMoveEvent(self, event):
        if self.start_x is not None and event.buttons() & Qt.LeftButton:
            self.preview.emit(max(220, min(900, round(self.start_width + event.globalPosition().x() - self.start_x))))
            event.accept()
    def mouseReleaseEvent(self, event):
        if self.start_x is not None and event.button() == Qt.LeftButton:
            self.committed.emit(self.column.width())
            self.start_x = None
            event.accept()
