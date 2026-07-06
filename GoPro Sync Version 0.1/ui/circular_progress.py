"""Eine runde, animierte Fortschritts-'Bubble' mit Prozentzahl und Datei-Zähler."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QWidget

from ui.theme import ACCENT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, SUCCESS


class CircularProgressBubble(QWidget):
    def __init__(self, diameter: int = 220, parent=None):
        super().__init__(parent)
        self._diameter = diameter
        self._value = 0.0          # 0..100, animiert
        self._target_value = 0.0
        self._current_index = 0
        self._total = 0
        self._status_text = "Bereit"
        self._done = False

        self.setFixedSize(diameter, diameter)

        self._anim = QPropertyAnimation(self, b"value")
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def getValue(self):
        return self._value

    def setValue(self, v):
        self._value = v
        self.update()

    value = Property(float, getValue, setValue)

    def set_progress(self, current: int, total: int, percent: int, status_text: str | None = None):
        self._current_index = current
        self._total = total
        self._done = total > 0 and current >= total
        if status_text is not None:
            self._status_text = status_text
        self._animate_to(percent)

    def set_idle(self, text: str = "Bereit"):
        self._current_index = 0
        self._total = 0
        self._done = False
        self._status_text = text
        self._animate_to(0)

    def set_complete(self, text: str = "Fertig!"):
        self._done = True
        self._status_text = text
        self._animate_to(100)

    def _animate_to(self, target: float):
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        stroke = max(10, int(side * 0.06))
        rect = QRectF(stroke / 2, stroke / 2, side - stroke, side - stroke)

        # Hintergrund-Ring
        bg_pen = QPen(QColor(BORDER))
        bg_pen.setWidth(stroke)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # Fortschritts-Ring
        color = QColor(SUCCESS if self._done else ACCENT)
        fg_pen = QPen(color)
        fg_pen.setWidth(stroke)
        fg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(fg_pen)
        span = int(-360 * 16 * (self._value / 100.0))
        painter.drawArc(rect, 90 * 16, span)

        # Prozent-Text
        painter.setPen(QColor(TEXT_PRIMARY))
        percent_font = QFont("Segoe UI", int(side * 0.16), QFont.Weight.Bold)
        painter.setFont(percent_font)
        percent_rect = QRectF(0, side * 0.30, side, side * 0.28)
        painter.drawText(percent_rect, Qt.AlignmentFlag.AlignCenter, f"{int(self._value)}%")

        # Datei-Zähler
        painter.setPen(QColor(TEXT_SECONDARY))
        sub_font = QFont("Segoe UI", int(side * 0.055))
        painter.setFont(sub_font)
        if self._total > 0:
            counter_text = f"{min(self._current_index, self._total)} von {self._total} Dateien"
        else:
            counter_text = self._status_text
        counter_rect = QRectF(side * 0.1, side * 0.56, side * 0.8, side * 0.14)
        painter.drawText(counter_rect, Qt.AlignmentFlag.AlignCenter, counter_text)

        # Status-Text unten (z.B. Dateiname oder "Fertig!")
        painter.setPen(QColor(TEXT_SECONDARY))
        status_font = QFont("Segoe UI", int(side * 0.045))
        painter.setFont(status_font)
        status_rect = QRectF(side * 0.08, side * 0.68, side * 0.84, side * 0.12)
        elided = painter.fontMetrics().elidedText(
            self._status_text, Qt.TextElideMode.ElideMiddle, int(side * 0.8)
        )
        painter.drawText(status_rect, Qt.AlignmentFlag.AlignCenter, elided)

        painter.end()
