"""🗓️ Set a card's labels, due time, reminders, and files."""
import copy
import os
from pathlib import Path
from PySide6.QtCore import Qt, QDateTime, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QCheckBox, QDateTimeEdit, QComboBox, QListWidget, QPushButton, QFileDialog, QMessageBox
from card_tools import clean_labels, label_text
from attachments import file_name, MAX_FILE_BYTES, MAX_PROJECT_BYTES
from file_io import atomic_write_bytes


class CardDetails(QWidget):
    def __init__(self, labels=None, due_at=None, reminder_at=None, attachments=None, store=None, budget=MAX_PROJECT_BYTES, parent=None, existing_hashes=None):
        super().__init__(parent)
        self.store = store
        self.budget = budget
        self.existing_hashes = set(existing_hashes or [])
        self.files = copy.deepcopy(attachments or [])
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel('🏷️ Labels — separate with commas'))
        self.labels_edit = QLineEdit(label_text(labels or []))
        self.labels_edit.setAccessibleName('Card labels')
        self.labels_edit.setPlaceholderText('Design, Client, Release')
        layout.addWidget(self.labels_edit)
        row = QHBoxLayout()
        self.due_check = QCheckBox('📅 Due')
        self.due_check.setChecked(due_at is not None)
        row.addWidget(self.due_check)
        self.due_edit = QDateTimeEdit()
        self.due_edit.setCalendarPopup(True)
        self.due_edit.setDisplayFormat('dd MMM yyyy HH:mm')
        self.due_edit.setAccessibleName('Due date and local time')
        self.due_edit.setDateTime(QDateTime.fromSecsSinceEpoch(int(due_at)) if due_at is not None else QDateTime.currentDateTime().addDays(1))
        self.due_edit.setEnabled(self.due_check.isChecked())
        self.due_check.toggled.connect(self.due_edit.setEnabled)
        row.addWidget(self.due_edit, 1); layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(QLabel('⏰ Remind me'))
        self.reminder_combo = QComboBox()
        for label, offset in [('No reminder', None), ('At the due time', 0), ('15 minutes before', 900), ('1 hour before', 3600), ('1 day before', 86400)]:
            self.reminder_combo.addItem(label, offset)
        if due_at is not None and reminder_at is not None:
            offset = int(due_at - reminder_at)
            index = self.reminder_combo.findData(offset)
            if index < 0:
                self.reminder_combo.addItem('Keep the saved reminder time', offset)
                index = self.reminder_combo.count() - 1
            self.reminder_combo.setCurrentIndex(index)
        self.reminder_combo.setEnabled(self.due_check.isChecked())
        self.due_check.toggled.connect(self.reminder_combo.setEnabled)
        row.addWidget(self.reminder_combo, 1); layout.addLayout(row)
        hint = QLabel('Times use your local timezone. Reminders work while WhiteBoard is open and catch up at launch.')
        hint.setWordWrap(True); layout.addWidget(hint)
        layout.addWidget(QLabel('📎 Attachments — copied locally, 25 MB each / 100 MB per project'))
        self.file_list = QListWidget(); self.file_list.setMaximumHeight(85)
        self.file_list.setAccessibleName('Card attachments')
        layout.addWidget(self.file_list)
        row = QHBoxLayout()
        for label, method in [('Add files…', self.add_files), ('Open…', self.open_file), ('Save copy…', self.save_file), ('Remove', self.remove_file)]:
            button = QPushButton(label); button.clicked.connect(method); row.addWidget(button)
            button.setEnabled(store is not None)
        layout.addLayout(row)
        self._refresh_files()
    def _refresh_files(self):
        row = self.file_list.currentRow(); self.file_list.clear()
        for entry in self.files:
            self.file_list.addItem(f"{entry['name']} · {entry['size'] / 1024:.1f} KB")
        if self.files:
            self.file_list.setCurrentRow(max(0, min(len(self.files) - 1, row)))
    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '📎 Add files')
        for path in paths:
            try:
                source = Path(path)
                name = file_name(source.name)
                size = source.stat().st_size
                if size > MAX_FILE_BYTES:
                    raise ValueError('Each attachment must be 25 MB or smaller.')
                self.files.append({'name': name, 'size': size, 'pending_path': os.fspath(source)})
            except (ValueError, OSError) as error:
                QMessageBox.warning(self, '⚠️ Could not attach the file', str(error))
        self._refresh_files()
    def _selected(self):
        index = self.file_list.currentRow()
        return self.files[index] if 0 <= index < len(self.files) else None
    def open_file(self):
        entry = self._selected()
        if not entry:
            return
        if QMessageBox.question(self, '🛡️ Open an attachment?', 'Only open files from people you trust. Open this file with its Windows app?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            path = Path(entry['pending_path']) if 'pending_path' in entry else self.store.open_copy(entry)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
                raise OSError('No app could open this file. Use Save copy instead.')
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, '⚠️ Could not open the file', str(error))
    def save_file(self):
        entry = self._selected()
        if not entry:
            return
        target, _ = QFileDialog.getSaveFileName(self, '💾 Save an attachment copy', entry['name'])
        if not target:
            return
        try:
            if 'pending_path' in entry:
                with open(entry['pending_path'], 'rb') as source:
                    data = source.read(MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    raise ValueError('The selected file is now larger than 25 MB.')
            else:
                data = self.store.read(entry)
            atomic_write_bytes(target, data)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, '⚠️ Could not save the copy', str(error))
    def remove_file(self):
        row = self.file_list.currentRow()
        if 0 <= row < len(self.files):
            self.files.pop(row); self._refresh_files()
    def prepare(self):
        clean_labels(self.labels_edit.text())
        due = self.due_edit.dateTime()
        if self.due_check.isChecked() and not due.isValid():
            raise ValueError('Choose a valid date and time.')
        prepared = []
        for entry in self.files:
            prepared.append(self.store.add(entry['pending_path']) if 'pending_path' in entry else dict(entry))
        if sum({a['sha256']: a['size'] for a in prepared if a['sha256'] not in self.existing_hashes}.values()) > self.budget:
            raise ValueError('Attachments must total 100 MB or less per project.')
        self.files = prepared
    def get_values(self):
        due_at = self.due_edit.dateTime().toSecsSinceEpoch() if self.due_check.isChecked() else None
        offset = self.reminder_combo.currentData()
        reminder_at = max(0, due_at - offset) if due_at is not None and offset is not None else None
        return {'labels': clean_labels(self.labels_edit.text()), 'due_at': due_at, 'reminder_at': reminder_at, 'attachments': copy.deepcopy(self.files)}
