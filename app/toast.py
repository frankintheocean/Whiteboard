"""🔔 Show short status messages inside the app."""
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint

import styles

# How long a toast stays fully visible before it starts fading out.
DEFAULT_DURATION_MS = 2600
# Fade in/out duration.
FADE_MS = 180
TOAST_SPACING = 8
TOAST_MARGIN = 16


class Toast(QWidget):
    """A single self-closing banner. Not a QDialog -- it never blocks
    input to the rest of the window, and it removes itself with no user
    action required."""

    def __init__(self, host: "ToastHost", text: str, kind: str = "info",
                 duration_ms: int = DEFAULT_DURATION_MS):
        super().__init__(host.parent_widget)
        self._host = host
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        # A plain QWidget doesn't paint its own stylesheet background/
        # border by default (unlike QFrame) -- without this, the
        # background-color/border rule in _apply_style() below is never
        # actually rendered, so the toast shows as bare text with no
        # visible box at all, in every theme.
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        icon = {"info": "\u2139\uFE0F", "success": "\u2705", "error": "\u274C"}.get(kind, "\u2139\uFE0F")
        label = QLabel(f"{icon} {text}")
        label.setTextFormat(Qt.PlainText)
        label.setObjectName("ToastLabel")
        label.setWordWrap(True)
        layout.addWidget(label)

        self._apply_style(kind)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.finished.connect(self._on_animation_finished)
        self._closing = False

        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self._start_fade_out)
        self._duration_ms = max(800, duration_ms)

    def _apply_style(self, kind: str):
        theme_id = getattr(self._host, "theme_id", styles.DEFAULT_THEME)
        t = styles.theme_colors(theme_id)
        border = {"error": t["danger"], "success": t["accent"]}.get(kind, t["border_strong"])
        self.setStyleSheet(
            f"""
            #Toast {{
                background-color: {t['surface']};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            #ToastLabel {{
                color: {t['text']};
                font-size: 13px;
                background: transparent;
            }}
            """
        )

    def show_animated(self):
        self.adjustSize()
        self.show()
        self._fade_anim.stop()
        self._closing = False
        self._fade_anim.setDuration(FADE_MS)
        self._fade_anim.setStartValue(self._opacity_effect.opacity())
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()
        self._close_timer.start(self._duration_ms)

    def _start_fade_out(self):
        self._closing = True
        self._fade_anim.stop()
        self._fade_anim.setDuration(FADE_MS)
        self._fade_anim.setStartValue(self._opacity_effect.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def _on_animation_finished(self):
        if self._closing:
            self._on_faded_out()

    def _on_faded_out(self):
        self._host._on_toast_closed(self)
        self.deleteLater()

    def dismiss_immediately(self):
        """Used when the host itself is being torn down -- skip the fade
        and just clean up, so a toast never outlives its parent window."""
        self._close_timer.stop()
        self._fade_anim.stop()
        self.hide()
        self.deleteLater()


class ToastHost:
    """Mixin-style helper object a QWidget (typically the main window)
    owns to manage a stack of Toast children positioned over itself.
    Not a QWidget itself -- it just tracks active toasts and repositions
    them, so it adds no extra widget to the Qt parent/child tree beyond
    the Toasts it creates."""

    def __init__(self, parent_widget: QWidget):
        self.parent_widget = parent_widget
        self.theme_id = styles.DEFAULT_THEME
        self._active_toasts = []

    def set_theme(self, theme_id: str):
        self.theme_id = theme_id

    def show_toast(self, text: str, kind: str = "info", duration_ms: int = DEFAULT_DURATION_MS):
        toast = Toast(self, text, kind=kind, duration_ms=duration_ms)
        self._active_toasts.append(toast)
        toast.show_animated()
        self._reposition()
        return toast

    def _on_toast_closed(self, toast: Toast):
        if toast in self._active_toasts:
            self._active_toasts.remove(toast)
        self._reposition()

    def _reposition(self):
        """Stack active toasts bottom-right of the parent window, most
        recent at the bottom, each one above the last."""
        if self.parent_widget is None:
            return
        try:
            parent_rect = self.parent_widget.rect()
        except RuntimeError:
            return
        y = parent_rect.height() - TOAST_MARGIN
        for toast in reversed(self._active_toasts):
            toast.adjustSize()
            y -= toast.height()
            x = parent_rect.width() - toast.width() - TOAST_MARGIN
            toast.move(max(0, x), max(0, y))
            toast.raise_()
            y -= TOAST_SPACING

    def dismiss_all(self):
        """Best-effort cleanup so no toast's fade-out timer tries to touch
        a host/window that's already being destroyed (e.g. on closeEvent)."""
        for toast in list(self._active_toasts):
            toast.dismiss_immediately()
        self._active_toasts = []
