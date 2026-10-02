"""The toggle switch control.

Liquid Glass uses switches where a setting is on/off, not tick boxes - they read
more directly and match the material.  This is a painted control rather than a
styled QCheckBox: a styled checkbox can round its indicator and draw a knob, but it
cannot animate between states or slide the knob, and its indicator square is the
thing that reads as "form" rather than "control".

The track is a capsule and the knob is a circle, both from the shared radius tokens,
so nothing here introduces a square corner.

Painted with QPainter rather than a stylesheet: the knob position is a continuous
value during the transition, which no stylesheet can express.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from . import gui_theme as theme

#: Track size.  Apple's switch is 51x31 points; this is the same proportion at the
#: desktop scale used by the rest of the interface.
TRACK_WIDTH = 42
TRACK_HEIGHT = 24
KNOB_MARGIN = 3
ANIMATION_MS = 140


class Switch(QWidget):
    """An iOS-style toggle: capsule track, circular knob, animated.

    Behaves like the ``QCheckBox`` it replaces where it matters - ``isChecked()``,
    ``setChecked()``, ``toggled`` - so call sites and tests keep working with
    ``setChecked`` and ``isChecked``.
    """

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("switch")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._checked = False
        #: 0.0 = knob fully left, 1.0 = fully right.  Animated, so it is not a bool.
        self._position = 0.0
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    # -- state ---------------------------------------------------------
    def isChecked(self) -> bool:  # noqa: N802 - Qt naming
        return self._checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt naming
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        self._animate_to(1.0 if checked else 0.0)
        self.toggled.emit(checked)

    def toggle(self) -> None:
        self.setChecked(not self._checked)

    def setCheckedSilently(self, checked: bool) -> None:  # noqa: N802 - Qt naming
        """Set the state without emitting ``toggled`` (for restoring defaults)."""
        self._checked = bool(checked)
        self._position = 1.0 if self._checked else 0.0
        self.update()

    # -- the animated knob position -------------------------------------
    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = float(value)
        self.update()

    position = Property(float, _get_position, _set_position)

    def _animate_to(self, target: float) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(target)
        self._animation.start()

    # -- interaction ---------------------------------------------------
    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.toggle()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- geometry ------------------------------------------------------
    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(TRACK_WIDTH, TRACK_HEIGHT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(TRACK_WIDTH, TRACK_HEIGHT)

    # -- painting ------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)

            # The track: a capsule.  Off is a sunken well, on is the accent.
            # theme.qcolor, not QColor("rgba(...)") - the CSS string form is invalid
            # for QColor and would paint nothing, which is exactly what happened.
            radius = self.height() / 2
            track = QRectF(0.0, 0.0, float(self.width()), float(self.height()))
            off = theme.qcolor(theme.SUNKEN_RGBA)
            on = QColor(theme.ACCENT)
            progress = max(0.0, min(1.0, self._position))
            painter.setBrush(
                QColor(
                    int(off.red() + (on.red() - off.red()) * progress),
                    int(off.green() + (on.green() - off.green()) * progress),
                    int(off.blue() + (on.blue() - off.blue()) * progress),
                    int(off.alpha() + (on.alpha() - off.alpha()) * progress),
                )
            )
            painter.drawRoundedRect(track, radius, radius)

            # A hairline so the off state keeps an edge against the glass.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(theme.qcolor(theme.BORDER_RGBA))
            painter.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

            # The knob: a circle, travelling from left to right.
            knob_size = float(self.height() - 2 * KNOB_MARGIN)
            travel = float(self.width() - knob_size - 2 * KNOB_MARGIN)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 245))
            painter.drawEllipse(
                QRectF(
                    KNOB_MARGIN + travel * progress,
                    float(KNOB_MARGIN),
                    knob_size,
                    knob_size,
                )
            )
        finally:
            painter.end()
