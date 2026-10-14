"""⏰ Deliver each scheduled card reminder once."""
import time
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QSystemTrayIcon, QApplication, QMenu
from card_tools import due_text


class ReminderService(QObject):
    delivered = Signal(list)
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.storage = window.storage
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QApplication.instance().windowIcon(), window)
            self.tray.setToolTip('WhiteBoard reminders')
            menu = QMenu(window)
            menu.addAction('Open WhiteBoard', self.show_window)
            menu.addAction('Quit WhiteBoard', window.close)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.show_window())
            self.tray.messageClicked.connect(self.show_window)
            self.tray.show()
        self.timer = QTimer(self)
        self.timer.setInterval(30000)
        self.timer.timeout.connect(self.check)
        self.timer.start()
        self.initial_timer = QTimer(self)
        self.initial_timer.setSingleShot(True)
        self.initial_timer.timeout.connect(self.check)
        self.initial_timer.start(1500)
    def show_window(self):
        self.window.showNormal(); self.window.raise_(); self.window.activateWindow()
    def check(self, now=None):
        now = time.time() if now is None else now
        pending = []
        for project in self.storage.projects:
            changed = False
            for card in project.cards:
                if card.due_at is not None and card.reminder_at is not None and card.reminder_at <= now and card.reminder_sent_at is None:
                    pending.append((project, card))
                    card.reminder_sent_at = now
                    changed = True
            if changed:
                self.storage.save_project(project.id)
        self.window.workspace.update_clock()
        if not pending:
            return []
        if len(pending) == 1:
            project, card = pending[0]
            message = f'{card.title} · {project.name}\nDue {due_text(card.due_at)}'
        else:
            message = f'{len(pending)} tasks have reminders. Open search or filter by due date to find them.'
        self.window._toast_host.show_toast(message, duration_ms=10000)
        if self.tray:
            self.tray.showMessage('WhiteBoard reminder', message, QSystemTrayIcon.Information, 10000)
        ids = [(p.id, c.id) for p, c in pending]
        self.delivered.emit(ids)
        return ids
    def stop(self):
        self.timer.stop(); self.initial_timer.stop()
        if self.tray:
            self.tray.hide()
