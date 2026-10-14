"""🌀 Shared wheel scrolling for the board and its columns."""
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtWidgets import QScrollArea, QApplication, QWidget


class SmoothScrollArea(QScrollArea):
    def __init__(self, parent=None, reduced_motion=False, orientation=Qt.Horizontal):
        super().__init__(parent)
        self._orientation = orientation
        self._bar = (self.verticalScrollBar() if orientation == Qt.Vertical
                     else self.horizontalScrollBar())
        self._anim = QPropertyAnimation(self._bar, b"value", self)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setDuration(220)
        self._target = None
        self._reduced_motion = reduced_motion
        self._anim.finished.connect(self._clear_target)
        self._bar.sliderPressed.connect(self.stop_scrolling)
        self._bar.actionTriggered.connect(self.stop_scrolling)
        # Child mouse events do not always propagate to the viewport.
        QApplication.instance().installEventFilter(self)

    def _clear_target(self):
        self._target = None

    def stop_scrolling(self):
        self._anim.stop()
        self._clear_target()

    def set_reduced_motion(self, enabled):
        self.stop_scrolling()
        self._reduced_motion = enabled

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick,
                            QEvent.KeyPress) and isinstance(watched, QWidget):
            if watched is self or self.isAncestorOf(watched):
                self.stop_scrolling()
        return super().eventFilter(watched, event)

    def wheelEvent(self, event):
        pixels = event.pixelDelta()
        angles = event.angleDelta()
        delta = (pixels.y() or pixels.x()) if not pixels.isNull() else (angles.y() or angles.x())
        if not delta or self._bar.maximum() == self._bar.minimum():
            super().wheelEvent(event)
            return
        current = self._target if self._target is not None else self._bar.value()
        target = max(self._bar.minimum(), min(self._bar.maximum(), current - delta))
        self._anim.stop()
        if self._reduced_motion or not pixels.isNull():
            self._clear_target()
            self._bar.setValue(target)
        else:
            self._target = target
            self._anim.setStartValue(self._bar.value())
            self._anim.setEndValue(target)
            self._anim.start()
        event.accept()


class SmoothVScrollArea(SmoothScrollArea):
    def __init__(self, parent=None, reduced_motion=False):
        super().__init__(parent, reduced_motion, Qt.Vertical)
