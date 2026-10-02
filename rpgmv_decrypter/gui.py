"""PySide6 desktop GUI for the RPG Maker MV/MZ decrypter.

Replaces the earlier Gradio web interface.  Three numbered steps in glass cards
(choose files, inspect, run), a results table, and a language switch that
retranslates the window in place.

Design notes
------------
* All validation, staging, batch running and output-folder rules live in
  :mod:`rpgmv_decrypter.ui_logic`, so this module is presentation only and the
  behaviour is testable without a display.
* :meth:`MainWindow.run_now` runs a batch **synchronously** and returns the
  :class:`~rpgmv_decrypter.ui_logic.RunResult`.  The buttons call
  :meth:`MainWindow._start_run`, which moves the *same* work onto a worker thread
  and feeds the *same* update path, so tests exercise what users run.
* The look is defined entirely by :mod:`rpgmv_decrypter.gui_theme` (palette,
  spacing, type scale, glass style) - no scattered magic numbers.

Usage::

    python -m rpgmv_decrypter.gui
    python -m rpgmv_decrypter.gui --lang en
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# Allow ``python rpgmv_decrypter/gui.py`` in addition to ``-m``.
if __package__ in (None, ""):  # pragma: no cover - only for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "rpgmv_decrypter"

try:  # pragma: no cover - exercised implicitly by every import
    from PySide6.QtCore import (
        QObject,
        QRect,
        QRectF,
        QSize,
        Qt,
        QThread,
        QTimer,
        Signal,
    )
    from PySide6.QtGui import (
        QAction,
        QBrush,
        QColor,
        QFont,
        QGuiApplication,
        QIcon,
        QIntValidator,
        QKeySequence,
        QLinearGradient,
        QPainter,
        QPen,
        QRadialGradient,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QComboBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSpinBox,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as error:  # pragma: no cover - depends on the environment
    raise ImportError(
        "The desktop interface needs PySide6.\n"
        'Install it with:  pip install "rpgmv-decrypter[gui]"\n'
        "or directly with:  pip install pyside6-essentials\n"
        f"(original error: {error})"
    ) from error

from . import ui_logic
from .decrypter import (
    DEFAULT_HEADER_LEN,
    DEFAULT_REMAIN,
    DEFAULT_SIGNATURE,
    DEFAULT_VERSION,
)
from .exceptions import DecrypterError
from .filetypes import DECRYPT_EXTENSIONS, ENCRYPT_EXTENSIONS, RpgMakerVersion, split_name
from .i18n import DEFAULT_LANGUAGE, LANGUAGES, tr
from .switch import Switch
from .ui_logic import (
    BatchRequest,
    BatchRunner,
    ProgressReport,
    RunResult,
    format_size,
)
from . import gui_theme as theme
from . import motion

__all__ = ["MainWindow", "RunWorker", "main"]

#: All extensions the window can take in one go.
_ANY_RESOURCE = DECRYPT_EXTENSIONS | ENCRYPT_EXTENSIONS

#: Which extensions each operation can actually process.
_MODE_EXTENSIONS: dict[str, frozenset[str]] = {
    "decrypt": DECRYPT_EXTENSIONS,
    "encrypt": ENCRYPT_EXTENSIONS,
    "restore": frozenset({"rpgmvp", "png_"}),
}

_MODE_BUTTON_KEY = {
    "decrypt": "run_decrypt",
    "encrypt": "run_encrypt_mv",
    "restore": "run_restore",
}

#: How many table rows are built per event-loop slice.  Building 3000 rows in one
#: go blocks the window for over a second; ~200 keeps each slice around 10-15 ms,
#: which is still far below the ~100 ms that starts to feel like a freeze.
_ROW_CHUNK = 200

#: Fixed widths for the type/size/status columns.  Must be fixed: automatic sizing
#: makes Qt measure every row on the first layout pass (see the table setup).
_COLUMN_WIDTHS = {1: 78, 2: 96, 3: 104}

#: How long the mono inline text may be clipped inside a hex field before the text
#: is cut off.  Checked by ``tools/check_text_fit.py`` so a longer key or a larger
#: font cannot silently reintroduce the clipping the user reported.
_MAX_MONO_CHARS = 32

#: Minimum width for a hex field: a full 16-byte key measures 208px in the mono font
#: at 10pt, and this keeps the field comfortably above that wherever it appears.
_HEX_FIELD_MIN_WIDTH = 230

#: The size the window opens at.  Measured rather than guessed: the steps row needs
#: 387px for its tallest card, and the previous 1240x840 only gave it 346px - the
#: fields were squashed and their text clipped, while a maximised window looked fine.
#: ``tools/measure_vertical_budget.py`` prints the account at any size and
#: ``tests/test_gui.py`` checks the default and the minimum.
_DEFAULT_WINDOW_SIZE = QSize(1360, 900)
#: Smallest size the layout still holds together at.  Measured: the files card needs
#: 303px of column height, which it only gets from a 880px-tall window, so a smaller
#: minimum would let the user shrink the window into the clipped state they reported.
#: ``tests/test_gui.py`` checks this boundary.
_MINIMUM_WINDOW_SIZE = QSize(1120, 880)

#: How long :meth:`MainWindow.wait_for_rows` waits for a listing before giving up.
_SCAN_TIMEOUT = 60.0


@dataclass(frozen=True)
class _FileFacts:
    """What the file table shows about one file, computed once per listing."""

    extension: str
    kind: str
    size: int
    size_text: str
    usable: bool


# ======================================================================
# glass widgets
# ======================================================================
def _mix_colour(first: str, second: str, amount: float) -> str:
    """Blend two ``#rrggbb`` or ``rgba(...)`` strings, for stylesheets built per frame.

    Animating a colour in Qt normally means a ``QVariantAnimation`` over ``QColor``, which
    is fine for a painted value but not for a *stylesheet* - the sheet takes a string.  So
    the interpolation happens here and the sheet is rebuilt from the result.  Alpha is
    carried through, which is what lets the dashed border and the fill fade together.
    """
    left, right = _parse_colour(first), _parse_colour(second)
    blended = tuple(
        int(round(a + (b - a) * min(max(amount, 0.0), 1.0)))
        for a, b in zip(left, right)
    )
    if blended[3] >= 255:
        return "#{:02x}{:02x}{:02x}".format(*blended[:3])
    return "rgba({}, {}, {}, {})".format(*blended)


def _parse_colour(spec: str) -> tuple[int, int, int, int]:
    """``#rrggbb`` or ``rgba(r, g, b, a)`` to a 4-tuple.  Anything odd becomes opaque grey."""
    text = spec.strip()
    if text.startswith("#"):
        digits = text.lstrip("#")
        if len(digits) == 6:
            return (
                int(digits[0:2], 16),
                int(digits[2:4], 16),
                int(digits[4:6], 16),
                255,
            )
        if len(digits) == 8:  # #aarrggbb, as Qt writes some colours
            return (
                int(digits[2:4], 16),
                int(digits[4:6], 16),
                int(digits[6:8], 16),
                int(digits[0:2], 16),
            )
    if text.startswith("rgba"):
        numbers = text[text.find("(") + 1 : text.rfind(")")].split(",")
        if len(numbers) == 4:
            try:
                return (
                    int(float(numbers[0])),
                    int(float(numbers[1])),
                    int(float(numbers[2])),
                    int(float(numbers[3])),
                )
            except ValueError:
                pass
    if text.startswith("rgb"):
        numbers = text[text.find("(") + 1 : text.rfind(")")].split(",")
        if len(numbers) == 3:
            try:
                return (int(float(numbers[0])), int(float(numbers[1])), int(float(numbers[2])), 255)
            except ValueError:
                pass
    return (128, 128, 128, 255)


class GlassPanel(QFrame):
    """A Liquid Glass card: translucent fill, specular rim, inner glow, soft shadow.

    The fill and shadow come from the stylesheet, but the *optics* - the lit top
    edge fading around the sides, and the soft glow just inside it - are painted in
    :meth:`paintEvent`.  Qt gives a border a single flat colour, so a stylesheet
    alone cannot produce the edge lighting that makes a surface read as glass
    rather than as a tinted rectangle.

    Two things about it move, and both are painted rather than applied as an effect:

    * it **arrives** - fades and rises, driven by :meth:`play_entrance`;
    * it **catches more light** when the pointer is over it, if it is interactive
      (:meth:`set_interactive`).

    :param object_name: ``objectName`` for the frame.  Passed explicitly because
        the glass stylesheet keys off it, so a subclass that renames itself (for
        tests to find it) must hand its own name over.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        object_name: str = "glass",
        radius: int = theme.RADIUS_LG,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.radius = radius
        self.setStyleSheet(theme.glass_style(selector=f'QFrame#{object_name}', radius=radius))
        theme.shadow(self, blur=44, y=12, alpha=175)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        #: Entrance progress, 0 (not there yet) .. 1 (settled).  Read by paintEvent.
        self._entrance = 1.0
        #: Highlight 0..1, following the pointer when the panel is interactive.
        self._hover = 0.0
        self._interactive = False
        self._hover_animation = motion.Animation(self._on_hover_frame, duration=motion.DURATION_QUICK)
        self.setMouseTracking(False)

    # -- entrance ------------------------------------------------------
    def set_entrance(self, value: float) -> None:
        """Set the arrival progress directly, for staggered entrances."""
        clamped = min(max(value, 0.0), 1.0)
        # The end states are always applied, whatever the step: the easing is asymptotic,
        # so its last frame can move by less than the threshold below - and skipping that
        # one left every surface fractionally un-settled (0.998) with nothing to correct
        # it.  A widget that is "almost" arrived is a bug, not a rounding detail.
        settled = clamped in (0.0, 1.0)
        if not settled and abs(clamped - self._entrance) < 0.002:
            return
        self._entrance = clamped
        self.update()

    @property
    def entrance(self) -> float:
        return self._entrance

    def play_entrance(self) -> None:
        """Fade and rise into place, once."""
        if not motion.motion_enabled():
            self.set_entrance(1.0)
            return
        self._entrance = 0.0
        animation = motion.Animation(self.set_entrance, duration=motion.DURATION_ENTRANCE, parent=self)
        animation.start()
        # Keep a reference: a QVariantAnimation that is garbage collected stops.
        self._entrance_animation = animation

    # -- highlight -----------------------------------------------------
    def set_interactive(self, interactive: bool) -> None:
        """Whether this panel lights up under the pointer."""
        self._interactive = interactive
        if interactive:
            self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            self.setCursor(Qt.CursorShape.ArrowCursor)

    @property
    def hover_amount(self) -> float:
        return self._hover

    def _on_hover_frame(self, value: float) -> None:
        self._hover = value
        self.update()

    def enterEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        if self._interactive:
            self._animate_hover(motion.DURATION_QUICK, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        if self._interactive:
            self._animate_hover(motion.DURATION_NORMAL, 0.0)
        super().leaveEvent(event)

    def _animate_hover(self, duration: int, target: float) -> None:
        if not motion.motion_enabled():
            self._hover = target
            self.update()
            return
        animation = motion.Animation(
            lambda value: self._on_hover_frame(value * target), duration=duration, parent=self
        )
        if target == 0.0:
            # Fade *out* from where it is, not from 1.
            start = self._hover
            animation = motion.Animation(
                lambda value: self._on_hover_frame(start * (1.0 - value)),
                duration=duration,
                parent=self,
            )
        animation.start()
        self._hover_animation = animation

    def _highlight(self) -> float:
        """The glow/rim multiplier: resting 1, highlighted up to ``HOVER_LIFT``."""
        if not self._interactive:
            return 1.0
        return 1.0 + (theme.HOVER_LIFT - 1.0) * self._hover

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        super().paintEvent(event)
        paint_glass_edges(
            self,
            self.radius,
            intensity=self._highlight(),
            opacity=self._entrance,
        )

    def paint_foreground(self) -> None:
        """Hook for subclasses that draw over the rim (the drop zone's highlight)."""


def paint_glass_edges(
    widget: QWidget,
    radius: int,
    *,
    glow: bool = True,
    intensity: float = 1.0,
    opacity: float = 1.0,
) -> None:
    """Paint the drop shadow, the inner glow and the specular rim.

    All three are *painted* rather than styled or applied as a graphics effect:

    * a ``QGraphicsDropShadowEffect`` renders the panel into an offscreen pixmap and
      caches the blur.  A panel containing a ``QScrollArea`` whose children keep
      repainting leaves stale copies of that text behind - the ghosting ("伪影") the
      user reported - so the shadow is stroked directly and cannot go stale;
    * Qt gives a border one flat colour, so a lit top edge fading around the sides
      cannot be expressed in a stylesheet at all.

    The two scale factors are what make the optics *animate*: a panel arriving fades in
    by way of ``opacity``, and a panel the pointer is over catches more light through
    ``intensity``.  Because these are read here rather than applied as an effect, the
    motion is part of the drawing and cannot go stale in a cache.

    Order, from the outside in:

    1. the drop shadow - concentric strokes hugging the outline;
    2. an inner glow so light bleeds inwards rather than stopping dead at the border;
    3. the specular rim - a 1px stroke from near-white at the lit top edge down to a
       faint hairline at the bottom.

    :param intensity: multiplier on the glow and rim, 0..1 for dimmed, 1 for resting,
        above 1 for a highlighted panel
    :param opacity: overall alpha, 0 for invisible
    """
    if opacity <= 0.004:
        return
    painter = QPainter(widget)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(min(max(opacity, 0.0), 1.0))
        rect = QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if rect.width() <= 2 or rect.height() <= 2:
            return
        painter.setBrush(Qt.BrushStyle.NoBrush)
        scale = max(intensity, 0.0)

        # 1. The shadow.  A widget cannot paint outside its own rect, so it is drawn
        #    as strokes just inside the outline, tapering outwards-in.  Against a
        #    dark backdrop it reads the same as an outset shadow.  The shadow does *not*
        #    follow the highlight: a panel catching more light does not cast more shade,
        #    and scaling both would read as the whole card inflating.
        for step in range(theme.SHADOW_SPREAD, 0, -1):
            fraction = step / theme.SHADOW_SPREAD
            alpha = int(theme.SHADOW_ALPHA * (1.0 - fraction) ** 1.4)
            if alpha <= 0:
                continue
            pen = QPen(QColor(0, 0, 0, alpha))
            pen.setWidthF(1.0)
            painter.setPen(pen)
            inset = rect.adjusted(step, step, -step, -step)
            if inset.width() > 2 and inset.height() > 2:
                painter.drawRoundedRect(inset, radius, radius)

        if glow:
            # 2. Inner glow: light bleeding inwards.  Kept faint - it sits on the
            #    surface text uses, so every point of alpha costs contrast.  The ceiling
            #    is enforced by tests/test_gui.py, which measures text on the lit card.
            for step, base_alpha in enumerate((8, 13, 18), start=1):
                alpha = int(base_alpha * scale)
                if alpha <= 0:
                    continue
                pen = QPen(QColor(255, 255, 255, min(alpha, 255)))
                pen.setWidthF(1.0)
                painter.setPen(pen)
                inset = rect.adjusted(step, step, -step, -step)
                if inset.width() > 2 and inset.height() > 2:
                    painter.drawRoundedRect(inset, radius - step, radius - step)

        # 3. The rim: bright where the light lands, dimming as the surface curves away.
        #    A single pixel wide, so it can be strong without hurting readability -
        #    this is the main carrier of the "this is glass" look.
        #    QPen needs a QBrush for a gradient stroke; a bare QLinearGradient is not
        #    an accepted overload.
        def lit(alpha: int) -> int:
            return max(0, min(255, int(alpha * scale)))

        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, QColor(255, 255, 255, lit(200)))
        gradient.setColorAt(0.22, QColor(255, 255, 255, lit(110)))
        gradient.setColorAt(0.7, QColor(255, 255, 255, lit(46)))
        gradient.setColorAt(1.0, QColor(255, 255, 255, lit(68)))
        pen = QPen(QBrush(gradient), 1.0)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, radius, radius)
    finally:
        painter.end()


class AuroraBackground(QWidget):
    """Paints the window backdrop the glass panels float above.

    Named for the aurora it used to paint; it now paints the dark backdrop with its
    light fields (see :func:`rpgmv_decrypter.gui_theme.paint_backdrop`).  ``opaque``
    follows the window: when a blurred Windows backdrop is active this widget paints
    only a scrim so the blur shows through, otherwise it paints the full colour so the
    window is never transparent by accident.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aurora")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._opaque = True

    def set_opaque(self, opaque: bool) -> None:
        self._opaque = opaque
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        try:
            theme.paint_backdrop(self, painter, opaque=self._opaque)
        finally:
            painter.end()


class StepCard(GlassPanel):
    """A glass card with a numbered badge, a title and a body of controls.

    The body is a plain layout with **no scroll area**: a settings column that needs
    a scrollbar is a layout failure rather than a feature, and the user said so.  The
    window's vertical split and the arrangement of the form are sized so the tallest
    card fits; ``tools/measure_vertical_budget.py`` prints that account and
    ``tests/test_gui.py`` fails if a card overflows again.

    The fields carry a minimum height because Qt resolves "not enough room" by
    shrinking the flexible widgets - which are exactly the text inputs.  They were
    pressed from 32px to 22px once, which sliced their glyphs in half.
    """

    def __init__(
        self,
        object_name: str,
        title_key: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, object_name=object_name)
        self.title_key = title_key

        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.SPACE_LG, theme.SPACE_MD, theme.SPACE_LG, theme.SPACE_MD)
        outer.setSpacing(theme.SPACE_MD)

        header = QHBoxLayout()
        header.setSpacing(theme.SPACE_SM)
        self.title_label = QLabel()
        self.title_label.setFont(theme.ui_font(size_role="title"))
        self.title_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.header = header
        outer.addLayout(header)

        # No scroll area.  A settings column that needs a scrollbar is a layout
        # failure rather than a feature - the user's words, and they are right.  The
        # window split and the form arrangement are sized so the tallest card fits;
        # tools/measure_vertical_budget.py prints the numbers and
        # tests/test_gui.py fails if a card ever overflows again.
        content = QWidget()
        content.setObjectName("cardBody")
        content.setStyleSheet("background: transparent;")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(theme.SPACE_SM)
        outer.addWidget(content, 1)


class SwitchRow(QWidget):
    """A labelled toggle: switch on the left, its label beside it.

    Replaces the tick boxes.  Liquid Glass uses switches for on/off settings, and a
    switch states its value at a glance where a tick box makes you look for the mark.
    The API mirrors ``QCheckBox`` where the call sites care - ``text()``,
    ``setText()``, ``isChecked()``, ``setChecked()``, ``toggled`` - so the wiring
    reads the same.
    """

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("switchRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.SPACE_SM)

        self.switch = Switch()
        self.label = QLabel()
        self.label.setFont(theme.ui_font())
        self.label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label, 1, Qt.AlignmentFlag.AlignVCenter)

        self.switch.toggled.connect(self.toggled.emit)

    # -- QCheckBox-compatible surface ----------------------------------
    def text(self) -> str:
        return self.label.text()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self.label.setText(text)

    def isChecked(self) -> bool:  # noqa: N802 - Qt naming
        return self.switch.isChecked()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt naming
        self.switch.setChecked(checked)

    def setCheckedSilently(self, checked: bool) -> None:  # noqa: N802 - Qt naming
        self.switch.setCheckedSilently(checked)

    def setToolTip(self, text: str) -> None:  # noqa: N802 - Qt naming
        self.setToolTip(text)
        self.switch.setToolTip(text)


class AdvancedDialog(QDialog):
    """The hex header settings, on their own surface.

    These four values (the header length plus the fake header's signature, version
    and remainder) are correct for essentially every game, and the restore action
    ignores them entirely - so they do not belong in the main column.  In a card they
    needed more height than the column has at the default window size and got
    squashed; here each field has the full width of the dialog.
    """

    def __init__(self, parent: QWidget | None = None, *, lang: str = DEFAULT_LANGUAGE) -> None:
        super().__init__(parent)
        self.setObjectName("advancedDialog")
        self.lang = lang
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.SPACE_LG, theme.SPACE_LG, theme.SPACE_LG, theme.SPACE_LG)
        outer.setSpacing(theme.SPACE_MD)

        self.title_label = QLabel()
        self.title_label.setFont(theme.ui_font(size_role="title"))
        self.title_label.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; background: transparent;"
        )
        outer.addWidget(self.title_label)

        self.hint = theme.HintLabel()
        self.hint_key = "hex_hint"
        outer.addWidget(self.hint)

        self.header_len_label = theme.FieldLabel()
        self.header_len_input = QLineEdit(str(DEFAULT_HEADER_LEN))
        self.header_len_input.setObjectName("headerLenInput")
        self.header_len_input.setFont(theme.mono_font())
        self.header_len_input.setValidator(QIntValidator(1, 4096, self))
        outer.addWidget(theme.group_field(self.header_len_label, self.header_len_input))

        self.signature_label = theme.FieldLabel()
        self.signature_input = QLineEdit(DEFAULT_SIGNATURE)
        self.signature_input.setObjectName("signatureInput")
        self.signature_input.setFont(theme.mono_font())
        outer.addWidget(theme.group_field(self.signature_label, self.signature_input))

        self.version_label = theme.FieldLabel()
        self.version_input = QLineEdit(DEFAULT_VERSION)
        self.version_input.setObjectName("versionInput")
        self.version_input.setFont(theme.mono_font())
        outer.addWidget(theme.group_field(self.version_label, self.version_input))

        self.remain_label = theme.FieldLabel()
        self.remain_input = QLineEdit(DEFAULT_REMAIN)
        self.remain_input.setObjectName("remainInput")
        self.remain_input.setFont(theme.mono_font())
        outer.addWidget(theme.group_field(self.remain_label, self.remain_input))

        # Qt does not enforce sizeHint on these flexible widgets, so a column short of
        # room squashes exactly them and slices their text - it did: Qt asked for 32px,
        # the layout gave 22px, and the glyphs were cut in half.  A hard floor on both
        # axes makes the text fit however the dialog is squeezed.
        for field in (
            self.header_len_input,
            self.signature_input,
            self.version_input,
            self.remain_input,
        ):
            field.setMinimumWidth(_HEX_FIELD_MIN_WIDTH)
            field.setMinimumHeight(theme.input_min_height())

        buttons = QHBoxLayout()
        buttons.setSpacing(theme.SPACE_SM)
        buttons.addStretch(1)
        self.reset_button = QPushButton()
        self.reset_button.setObjectName("resetButton")
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.clicked.connect(self.reset_to_defaults)
        self.close_button = QPushButton()
        self.close_button.setObjectName("closeAdvancedButton")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.accept)
        for button in (self.reset_button, self.close_button):
            buttons.addWidget(button)
        outer.addLayout(buttons)

    def header_len_value(self) -> int:
        """The header length typed in, or the default when it is unusable."""
        text = self.header_len_input.text().strip()
        try:
            value = int(text)
        except ValueError:
            return DEFAULT_HEADER_LEN
        return value if 1 <= value <= 4096 else DEFAULT_HEADER_LEN

    def reset_to_defaults(self) -> None:
        self.header_len_input.setText(str(DEFAULT_HEADER_LEN))
        self.signature_input.setText(DEFAULT_SIGNATURE)
        self.version_input.setText(DEFAULT_VERSION)
        self.remain_input.setText(DEFAULT_REMAIN)

    def retranslate(self, lang: str) -> None:
        self.setWindowTitle(tr("advanced_title", lang))
        self.title_label.setText(tr("advanced_title", lang))
        self.hint.setText(tr(self.hint_key, lang))
        self.header_len_label.setText(tr("header_len", lang))
        self.signature_label.setText(tr("signature", lang))
        self.version_label.setText(tr("version_field", lang))
        self.remain_label.setText(tr("remain", lang))
        self.reset_button.setText(tr("reset_defaults", lang))
        self.close_button.setText(tr("close", lang))


class DropZone(QWidget):
    """File list area that also accepts drag & drop."""

    paths_dropped = Signal(list)

    def __init__(self, hint: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        #: How strongly the drop target is lit, 0..1.  Driven by the pulse while a drag
        #: is over it; kept as state so a test can read it rather than guess from pixels.
        self._drag_glow = 0.0
        self._drag_pulse = motion.Pulse(lambda _phase: None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.SPACE_SM)

        self.table = QTableWidget(0, 4, self)
        self.table.setObjectName("fileTable")
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Fixed widths for the small columns on purpose.  ResizeToContents makes Qt
        # measure every row's text on the first layout pass, which blocked the event
        # loop for 4.5 s on a 3000-file folder (measured with
        # tools/benchmark_ui_freeze.py); fixed widths bring that to ~40 ms.  The
        # full path and size stay available as a tooltip on the name cell.
        for column, width in _COLUMN_WIDTHS.items():
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        self.table.setShowGrid(False)
        layout.addWidget(self.table, 1)

        self.hint = QLabel(hint)
        self.hint.setFont(theme.ui_font(size_role="caption"))
        self.hint.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; background: transparent;"
            f" border: 1px dashed {theme.GLASS_BORDER_SOFT}; border-radius: {theme.RADIUS_SM}px;"
            f" padding: {theme.SPACE_SM}px;"
        )
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint)

    # ------------------------------------------------------------------
    # the drop target's highlight
    # ------------------------------------------------------------------
    #: The highlight's own colours, interpolated by :meth:`_apply_drag_glow` rather than
    #: swapped in a stylesheet.  A stylesheet swap snaps and re-polishes every child;
    #: rewriting one small rule per frame is cheap and can be animated.
    _DRAG_GLOW_MS = 900

    def _drag_glow_style(self, amount: float) -> str:
        """The hint's stylesheet at a given highlight strength, 0..1.

        The border colour and the fill are mixed towards the accent so the hint visibly
        *catches light* as files come over it - a state change of one property, which is
        what the eye follows.

        At zero the fill is written as ``transparent`` rather than as a zero-alpha
        ``rgba``: the two look identical but compare unequal as strings, so the resting
        state would never match the style the widget started with.
        """
        clamped = min(max(amount, 0.0), 1.0)
        border = _mix_colour(theme.GLASS_BORDER_SOFT, theme.ACCENT, clamped)
        fill = "transparent" if clamped <= 0.001 else f"rgba(93, 118, 186, {int(40 * clamped)})"
        text = theme.TEXT_PRIMARY if clamped > 0.4 else theme.TEXT_MUTED
        return (
            f"color: {text}; background: {fill};"
            f" border: 1px dashed {border}; border-radius: {theme.RADIUS_SM}px;"
            f" padding: {theme.SPACE_SM}px;"
        )

    def _set_drag_glow(self, amount: float) -> None:
        self._drag_glow = amount
        self.hint.setStyleSheet(self._drag_glow_style(amount))

    def _pulse_frame(self, phase: float) -> None:
        """Breathe between a settled highlight and a slightly stronger one.

        A constant highlight reads as "stuck"; the pulse is what says the drop target is
        *live* and waiting for the file to be released.
        """
        self._set_drag_glow(0.72 + 0.28 * phase)

    def dragEnterEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            # Settle to full immediately, then breathe around it: the highlight has to be
            # unmistakable the moment the file is over the target, not 400 ms later.
            self._set_drag_glow(1.0)
            self._drag_pulse = motion.Pulse(
                self._pulse_frame, period_ms=self._DRAG_GLOW_MS
            )
            self._drag_pulse.start()

    def dragLeaveEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        self._drag_pulse.stop()
        # Reset *after* stopping: the pulse's last frame left the highlight wherever the
        # wave happened to be, so relying on the stop alone stranded it part-lit.
        self._reset_hint()

    def dropEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self._drag_pulse.stop()
        self._reset_hint()
        if paths:
            self.paths_dropped.emit(paths)
        event.acceptProposedAction()

    def _reset_hint(self) -> None:
        self._set_drag_glow(0.0)


# ======================================================================
# worker
# ======================================================================
class RunWorker(QObject):
    """Runs one batch on a worker thread and reports progress through signals."""

    started_run = Signal(int)
    progressed = Signal(int, int, str)
    finished_run = Signal(object)  # RunResult

    def __init__(self, request: BatchRequest, stop_event: threading.Event) -> None:
        super().__init__()
        self._request = request
        self._stop_event = stop_event

    def run(self) -> None:
        report = ProgressReport(
            on_start=self.started_run.emit,
            on_progress=lambda done, total, name: self.progressed.emit(done, total, name),
            should_stop=self._stop_event.is_set,
        )
        try:
            outcome = BatchRunner(report).run(self._request)
        except Exception as error:  # pragma: no cover - last-resort guard
            outcome = RunResult(
                result=ui_logic.RestoreResult(),
                run_directory=Path(),
                error=f"{type(error).__name__}: {error}",
            )
        self.finished_run.emit(outcome)


class ScanWorker(QObject):
    """Walks the picked folders off the GUI thread and streams rows back.

    Listing a large game takes real time (measured: ~620 ms for 20 000 files), all
    of it disk work, and doing it on the GUI thread freezes the window.  This
    walks, inspects (``stat`` + extension) and emits in batches so the table fills
    progressively while the event loop keeps running.
    """

    batch_ready = Signal(object, object)  # list[Path], list[_FileFacts]
    finished_scan = Signal(int, str)  # file count, error text ("" when fine)

    def __init__(
        self,
        inputs: Sequence[Path],
        *,
        recursive: bool,
        mode: str,
        excluded: set[str],
        batch_size: int = _ROW_CHUNK,
        inspect: Any = None,
    ) -> None:
        super().__init__()
        self._inputs = list(inputs)
        self._recursive = recursive
        self._mode = mode
        self._excluded = set(excluded)
        self._batch_size = batch_size
        # Injected so the expensive per-file inspection can be unit-tested, and so
        # this module stays importable without a QApplication.
        self._inspect = inspect

    def run(self) -> None:
        total = 0
        error = ""
        try:
            paths = ui_logic.expand_directories(self._inputs, recursive=self._recursive)
            if self._excluded:
                paths = [p for p in paths if ui_logic._scan_key(p) not in self._excluded]

            allowed = _MODE_EXTENSIONS.get(self._mode, DECRYPT_EXTENSIONS)
            for start in range(0, len(paths), self._batch_size):
                chunk = paths[start : start + self._batch_size]
                facts = [
                    self._inspect(path, allowed) if self._inspect else gui_inspect(path, allowed)
                    for path in chunk
                ]
                total += len(chunk)
                self.batch_ready.emit(chunk, facts)
        except Exception as unexpected:  # pragma: no cover - last-resort guard
            error = f"{type(unexpected).__name__}: {unexpected}"
        self.finished_scan.emit(total, error)


def gui_inspect(path: Path, allowed: frozenset[str]) -> _FileFacts:
    """Everything the table needs about one file, read exactly once.

    Module level (not a method) so the scan worker can call it off-thread without
    touching the widget.
    """
    extension = split_name(path)[1]
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return _FileFacts(
        extension=extension,
        kind=f".{extension}" if extension else "-",
        size=size,
        size_text=format_size(size),
        usable=extension in allowed,
    )


# ======================================================================
# main window
# ======================================================================
class MainWindow(QMainWindow):
    """The application window.

    :param lang: starting language, ``"zh"`` (default) or ``"en"``
    """

    def __init__(self, lang: str = DEFAULT_LANGUAGE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MainWindow")
        self.setWindowTitle(tr("app_title", lang))
        # Sized so the tallest card fits without squashing its controls: the steps row
        # needs 387px, and at 1240x840 it only got 346px, which clipped the hex fields
        # (the user saw this at the default size while a maximised window looked fine).
        self.resize(_DEFAULT_WINDOW_SIZE)
        self.setMinimumSize(_MINIMUM_WINDOW_SIZE)
        self.setAcceptDrops(True)

        self.lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
        self.last_run: RunResult | None = None
        #: Which OS backdrop the window ended up with, set on first show.
        self.backdrop_kind: str = "not applied"

        #: The hex header settings, in their own dialog.  Created up front so the
        #: ``*_input`` names below are always available; shown on demand.
        self.advanced = AdvancedDialog(self, lang=self.lang)

        self._init_state()

    # The hex fields now live in the dialog, but they are read and written all over
    # this module (and by the tests), so they stay exposed under the same names.
    @property
    def header_len_input(self) -> QLineEdit:
        return self.advanced.header_len_input

    @property
    def signature_input(self) -> QLineEdit:
        return self.advanced.signature_input

    @property
    def version_input(self) -> QLineEdit:
        return self.advanced.version_input

    @property
    def remain_input(self) -> QLineEdit:
        return self.advanced.remain_input

    @property
    def reset_button(self) -> QPushButton:
        return self.advanced.reset_button

    def _init_state(self) -> None:
        """Set up the mutable state.  Separate from ``__init__`` so the delegating
        properties above cannot split the constructor in two."""
        self._paths: list[Path] = []
        #: What the user actually picked: files as-is, folders kept as folders so
        #: the listing can be re-expanded when the recursion toggle changes.
        self._inputs: list[Path] = []
        #: Resolved paths the user removed by hand.  A folder expands again when
        #: the recursion toggle flips, and without this a removed row would come
        #: back from the folder that contains it.
        self._excluded: set[Path] = set()
        #: Per-file table data, computed once when the listing is built.
        self._row_facts: list[_FileFacts] = []
        #: Rows still waiting to be drawn, or None when the table is complete.
        self._pending_rows: list[int] | None = None
        #: Rows still waiting to be re-labelled after a language switch.
        self._pending_relabel: list[int] = []
        #: The background listing, while one is running.
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._scan_expected = 0
        #: Bumped per listing so a cancelled scan's queued batches are ignored.
        self._scan_generation = 0
        self._mode = "decrypt"
        #: Which engine naming the last "encrypt" run used (MV or MZ).
        self._version = RpgMakerVersion.MV
        self._stop_event = threading.Event()
        self._worker_thread: QThread | None = None
        self._worker: RunWorker | None = None
        self._retranslate: list[tuple[Any, str, str]] = []
        self._status_key: tuple[str, dict[str, Any]] | None = None
        #: The arrival animation, kept so it is not garbage collected mid-flight.
        self.entrance: motion.Stagger | None = None
        #: Whether the "results are going somewhere else" note has been logged yet.
        self._relocation_announced = False

        self._build_ui()
        self._apply_theme()
        _bind_all(self)
        self.set_language(self.lang)
        self._refresh_file_count()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = AuroraBackground(self)
        self.aurora = root
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(theme.SPACE_LG, theme.SPACE_LG, theme.SPACE_LG, theme.SPACE_LG)
        outer.setSpacing(theme.SPACE_MD)

        self.header_panel = self._build_header()
        outer.addWidget(self.header_panel)
        # The steps row is the tallest content (a settings column), so it gets the
        # larger share: at 3:4 the cards were given 322px for 294px of content and
        # grew scrollbars.  The results panel below still has room for its table and
        # log, which scroll on their own.
        outer.addWidget(self._build_steps(), 5)
        outer.addWidget(self._build_results(), 4)

        self._install_shortcuts()

    # ---- header ------------------------------------------------------
    def _build_header(self) -> QWidget:
        header = GlassPanel()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(theme.SPACE_LG, theme.SPACE_MD, theme.SPACE_LG, theme.SPACE_MD)
        layout.setSpacing(theme.SPACE_MD)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = QLabel()
        self.title_label.setFont(theme.ui_font(size_role="display"))
        self.title_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent;")
        self.subtitle_label = QLabel()
        self.subtitle_label.setFont(theme.ui_font(size_role="subtitle"))
        self.subtitle_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; background: transparent;")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        layout.addLayout(titles)
        layout.addStretch(1)

        # There was a green "完全离线" (fully offline) badge here.  It said nothing the
        # user needs: the tool never had a network feature, so the badge was claiming
        # credit for the absence of something that was never offered.

        self.language_label = QLabel()
        self.language_label.setFont(theme.ui_font(size_role="label"))
        self.language_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; background: transparent;")
        layout.addWidget(self.language_label)

        self.language_combo = QComboBox()
        self.language_combo.setObjectName("languageCombo")
        self.language_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.language_combo.setMinimumHeight(theme.input_min_height())
        for code, label in LANGUAGES.items():
            self.language_combo.addItem(label, code)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        layout.addWidget(self.language_combo)
        return header

    # ---- steps -------------------------------------------------------
    def _build_steps(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.SPACE_MD)

        self.key_card = self._build_key_card()
        self.files_card = self._build_files_card()
        self.options_card = self._build_options_card()
        #: The three numbered steps, in order.  Also the arrival order.
        self.step_cards = [self.key_card, self.files_card, self.options_card]
        for card in self.step_cards:
            # They hold no controls of their own to click, but they do take the pointer,
            # and catching a little more light is what makes them feel like surfaces
            # rather than printed rectangles.
            card.set_interactive(True)
        layout.addWidget(self.key_card, 3)
        layout.addWidget(self.files_card, 4)
        layout.addWidget(self.options_card, 3)
        return container

    def _surfaces(self) -> list[Any]:
        """Every glass surface, in the order it should arrive."""
        return [self.header_panel, *self.step_cards, self.results_panel]

    def play_entrance(self) -> None:
        """Run the arrival: the surfaces fade and rise in sequence.

        One :class:`motion.Stagger` drives them all, so the order is visible without
        several timers racing each other - and when motion is off it settles every
        surface on its end state in one go, so the window looks exactly the same.
        """
        panels = self._surfaces()
        for panel in panels:
            panel.set_entrance(0.0)

        def on_frame(index: int, value: float) -> None:
            panels[index].set_entrance(value)

        self.entrance = motion.Stagger(on_frame, len(panels))
        self.entrance.start()

    def _build_key_card(self) -> QWidget:
        card = StepCard("stepKey", "step_key")

        self.key_source_row = QWidget()
        row = QHBoxLayout(self.key_source_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACE_SM)
        self.detect_button = QPushButton()
        self.detect_button.setObjectName("detectButton")
        self.detect_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detect_button.clicked.connect(self._on_detect_key)
        row.addWidget(self.detect_button)
        card.body.addWidget(self.detect_button)

        self.key_source_label = theme.HintLabel()
        card.body.addWidget(self.key_source_label)

        self.key_label = theme.FieldLabel()
        card.body.addWidget(self.key_label)

        key_row = QHBoxLayout()
        key_row.setSpacing(theme.SPACE_XS)
        self.key_field = QLineEdit()
        self.key_field.setObjectName("keyField")
        self.key_field.setFont(theme.mono_font())
        self.key_field.setClearButtonEnabled(True)
        self.key_field.setMinimumHeight(theme.input_min_height())
        self.key_field.textChanged.connect(self._refresh_file_count)
        key_row.addWidget(self.key_field, 1)
        card.body.addLayout(key_row)

        buttons = QHBoxLayout()
        buttons.setSpacing(theme.SPACE_XS)
        self.copy_key_button = QPushButton()
        self.copy_key_button.setObjectName("copyKeyButton")
        self.copy_key_button.clicked.connect(self._on_copy_key)
        self.clear_key_button = QPushButton()
        self.clear_key_button.setObjectName("clearKeyButton")
        self.clear_key_button.clicked.connect(self.key_field.clear)
        for button in (self.copy_key_button, self.clear_key_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch(1)
        card.body.addLayout(buttons)

        self.key_hint = theme.HintLabel()
        card.body.addWidget(self.key_hint)
        card.body.addStretch(1)
        return card

    def _build_files_card(self) -> QWidget:
        card = StepCard("stepFiles", "step_files")

        buttons = QHBoxLayout()
        buttons.setSpacing(theme.SPACE_SM)
        self.add_files_button = QPushButton()
        self.add_files_button.setObjectName("addFilesButton")
        self.add_files_button.clicked.connect(self._on_add_files)
        self.add_folder_button = QPushButton()
        self.add_folder_button.setObjectName("addFolderButton")
        self.add_folder_button.clicked.connect(self._on_add_folder)
        self.remove_button = QPushButton()
        self.remove_button.setObjectName("removeButton")
        self.remove_button.clicked.connect(self._on_remove_selected)
        self.clear_button = QPushButton()
        self.clear_button.setObjectName("clearButton")
        self.clear_button.clicked.connect(self._on_clear_files)
        for button in (
            self.add_files_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
        ):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch(1)
        card.body.addLayout(buttons)

        self.drop_zone = DropZone(tr("drag_hint", self.lang))
        self.drop_zone.paths_dropped.connect(self.add_paths)
        self.file_table = self.drop_zone.table
        self.drop_hint = self.drop_zone.hint
        card.body.addWidget(self.drop_zone, 1)

        self.count_label = theme.HintLabel()
        card.body.addWidget(self.count_label)
        return card

    def _build_options_card(self) -> QWidget:
        card = StepCard("stepOptions", "step_run")

        self.verify_check = SwitchRow()
        self.verify_check.setChecked(True)
        self.verify_check.toggled.connect(self._refresh_file_count)
        card.body.addWidget(self.verify_check)

        self.verify_hint = theme.HintLabel()
        card.body.addWidget(self.verify_hint)

        # The hex fields live in a dialog, not in this column.  Two reasons: the card
        # cannot hold them at the default window size without squashing them (it
        # needed 294px in 284px, which clipped their text), and they are rarely
        # touched - the defaults are correct for essentially every game.  Keeping
        # them out is what lets the card stay uncluttered and fit at any size.
        self.advanced_button = QPushButton()
        self.advanced_button.setObjectName("advancedButton")
        self.advanced_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.advanced_button.clicked.connect(self._on_advanced)
        self.advanced_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        card.body.addWidget(self.advanced_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.recursive_check = SwitchRow()
        self.recursive_check.setChecked(True)
        self.recursive_check.toggled.connect(self._on_recursive_toggled)
        card.body.addWidget(self.recursive_check)

        self.package_zip_check = SwitchRow()
        self.package_zip_check.setChecked(False)
        card.body.addWidget(self.package_zip_check)

        self.zip_hint = theme.HintLabel()
        self.zip_hint_key = "package_zip_hint"
        card.body.addWidget(self.zip_hint)

        card.body.addStretch(1)
        return card

    # ---- results -----------------------------------------------------
    def _build_results(self) -> QWidget:
        card = GlassPanel()
        self.results_panel = card
        layout = QVBoxLayout(card)
        layout.setContentsMargins(theme.SPACE_LG, theme.SPACE_MD, theme.SPACE_LG, theme.SPACE_MD)
        layout.setSpacing(theme.SPACE_SM)

        head = QHBoxLayout()
        head.setSpacing(theme.SPACE_SM)
        self.results_label = QLabel()
        self.results_label.setFont(theme.ui_font(size_role="title"))
        self.results_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent;")
        head.addWidget(self.results_label)
        head.addStretch(1)

        self.output_label = theme.HintLabel()
        head.addWidget(self.output_label)
        self.change_output_button = QPushButton()
        self.change_output_button.setObjectName("changeOutputButton")
        self.change_output_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_output_button.clicked.connect(self._on_change_output)
        head.addWidget(self.change_output_button)
        layout.addLayout(head)

        self.output_root_label = theme.HintLabel()
        layout.addWidget(self.output_root_label)

        # progress line
        progress_row = QHBoxLayout()
        progress_row.setSpacing(theme.SPACE_SM)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_row.addWidget(self.progress_bar, 1)
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        self.status_label.setFont(theme.ui_font(size_role="body"))
        self.status_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; background: transparent;")
        self.status_label.setMinimumWidth(260)
        progress_row.addWidget(self.status_label)
        layout.addLayout(progress_row)

        # actions
        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACE_SM)
        self.run_decrypt_button = QPushButton()
        self.run_decrypt_button.setObjectName("runDecryptButton")
        self.run_decrypt_button.setProperty("accent", True)
        self.run_decrypt_button.clicked.connect(lambda: self._start_run("decrypt"))
        self.run_encrypt_mv_button = QPushButton()
        self.run_encrypt_mv_button.setObjectName("runEncryptMvButton")
        self.run_encrypt_mv_button.clicked.connect(
            lambda: self._start_run("encrypt", RpgMakerVersion.MV)
        )
        self.run_encrypt_mz_button = QPushButton()
        self.run_encrypt_mz_button.setObjectName("runEncryptMzButton")
        self.run_encrypt_mz_button.clicked.connect(
            lambda: self._start_run("encrypt", RpgMakerVersion.MZ)
        )
        self.run_restore_button = QPushButton()
        self.run_restore_button.setObjectName("runRestoreButton")
        self.run_restore_button.clicked.connect(lambda: self._start_run("restore"))
        self.cancel_button = QPushButton()
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._on_cancel)
        #: Shows the results inside this window.  Asking the operating system's shell to
        #: show a folder is refused outright by a restricted session (ShellExecute error
        #: 5), and no phrasing of that request gets around it.  A window of our own needs
        #: no shell, so the results stay reachable.
        self.browse_results_button = QPushButton()
        self.browse_results_button.setObjectName("browseResultsButton")
        self.browse_results_button.clicked.connect(self._on_browse_results)
        self.copy_report_button = QPushButton()
        self.copy_report_button.setObjectName("copyReportButton")
        self.copy_report_button.clicked.connect(self._on_copy_report)

        for button in (
            self.run_decrypt_button,
            self.run_encrypt_mv_button,
            self.run_encrypt_mz_button,
            self.run_restore_button,
            self.cancel_button,
            self.browse_results_button,
            self.copy_report_button,
        ):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setFont(theme.mono_font())
        self.log_view.setMinimumHeight(120)
        layout.addWidget(self.log_view, 1)
        return card

    def _install_shortcuts(self) -> None:
        for sequence, slot in (
            ("Ctrl+O", self._on_add_files),
            ("Ctrl+Shift+O", self._on_add_folder),
            ("Ctrl+R", lambda: self._start_run(self._mode)),
            ("Ctrl+D", self._on_detect_key),
            ("Ctrl+L", self._on_clear_files),
        ):
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(slot)
            self.addAction(action)

    # ------------------------------------------------------------------
    # theming
    # ------------------------------------------------------------------
    def _apply_theme(self) -> None:
        """The widget stylesheet.

        Metrics follow Liquid Glass: generous radii, capsule buttons, and *inset*
        wells for inputs and tables (darker than the window, so they read as
        recesses rather than as raised chips).  Panels get their edge lighting from
        :func:`paint_glass_edges` instead, because a stylesheet border is one flat
        colour.
        """
        self.setStyleSheet(
            f"""
            QMainWindow {{ background: transparent; }}
            QLabel {{ background: transparent; }}
            QLineEdit, QSpinBox, QComboBox {{
                background: {theme.GLASS_FILL_SUNKEN};
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.GLASS_BORDER_SOFT};
                border-radius: {theme.RADIUS_SM}px;
                padding: 7px 10px;
                selection-background-color: {theme.ACCENT};
                selection-color: #ffffff;
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border: 1px solid {theme.ACCENT};
                background: rgba(0, 0, 0, 120);
            }}
            QLineEdit:disabled, QSpinBox:disabled {{ color: {theme.TEXT_MUTED}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background: #2c2c2e;
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.GLASS_BORDER};
                border-radius: {theme.RADIUS_SM}px;
                selection-background-color: {theme.ACCENT};
                selection-color: #ffffff;
                padding: 4px;
            }}
            /* Capsule buttons: Liquid Glass controls are pill-shaped and float.
               The minimum height stops a tight column from squashing them - the
               same trap that sliced the text fields. */
            QPushButton {{
                background: {theme.GLASS_FILL_STRONG};
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.GLASS_BORDER};
                border-radius: {theme.RADIUS_CAPSULE}px;
                padding: 8px 16px;
                font-weight: 500;
                min-height: {theme.input_min_height()}px;
            }}
            QPushButton:hover {{ background: rgba(255, 255, 255, 64); border-color: {theme.GLASS_EDGE}; }}
            QPushButton:pressed {{ background: rgba(255, 255, 255, 26); }}
            QPushButton:disabled {{ color: {theme.TEXT_MUTED}; border-color: {theme.GLASS_BORDER_SOFT}; }}
            QPushButton[accent="true"] {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {theme.ACCENT_HOVER}, stop:1 {theme.ACCENT_PRESSED});
                border: 1px solid rgba(255,255,255,110);
                color: {theme.ACCENT_TEXT};
                font-weight: 600;
                padding: 8px 20px;
            }}
            /* Hover must not open the fill up: every stop of every accent state
               keeps the label above WCAG AA (tests/test_gui.py checks the palette;
               tools/tune_liquid_glass.py prints the ratios). */
            QPushButton[accent="true"]:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {theme.ACCENT_HOVER}, stop:1 {theme.ACCENT});
                border: 1px solid {theme.GLASS_EDGE};
            }}
            QPushButton[accent="true"]:pressed {{
                background: {theme.ACCENT_PRESSED};
            }}
            /* Switches are painted by rpgmv_decrypter.switch, so there is no
               QCheckBox rule any more - the old one left a 5px radius on a 17px
               square, which read as a form control rather than Liquid Glass. */
            QGroupBox {{
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.GLASS_BORDER_SOFT};
                border-radius: {theme.RADIUS_MD}px;
                margin-top: 10px;
                padding: 10px;
            }}
            QTableWidget {{
                background: {theme.GLASS_FILL_SUNKEN};
                alternate-background-color: rgba(255,255,255,10);
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.GLASS_BORDER_SOFT};
                border-radius: {theme.CONTROL_RADIUS}px;
                gridline-color: transparent;
                selection-background-color: rgba(93,118,186,120);
                selection-color: #ffffff;
            }}
            QTableWidget::item {{ padding: 5px 8px; }}
            QHeaderView::section {{
                background: rgba(255,255,255,18);
                color: {theme.TEXT_SECONDARY};
                border: none;
                border-bottom: 1px solid {theme.GLASS_BORDER_SOFT};
                padding: 7px 8px;
                font-weight: 600;
            }}
            QProgressBar {{
                background: {theme.GLASS_FILL_SUNKEN};
                border: 1px solid {theme.GLASS_BORDER_SOFT};
                border-radius: {theme.CONTROL_RADIUS}px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {theme.ACCENT}, stop:1 {theme.ACCENT_SKY});
                border-radius: {theme.CONTROL_RADIUS}px;
            }}
            QPlainTextEdit {{
                background: {theme.GLASS_FILL_SUNKEN};
                color: {theme.TEXT_SECONDARY};
                border: 1px solid {theme.GLASS_BORDER_SOFT};
                border-radius: {theme.CONTROL_RADIUS}px;
                padding: 10px;
            }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,60); border-radius: {theme.RADIUS_CAPSULE}px; min-height: 28px;
            }}
            QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,95); }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
            QScrollBar::handle:horizontal {{
                background: rgba(255,255,255,60); border-radius: {theme.RADIUS_CAPSULE}px; min-width: 28px;
            }}
            QToolTip {{
                background: #101a2c; color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.GLASS_BORDER};
                border-radius: {theme.RADIUS_MD}px; padding: 6px;
            }}
            """
        )
        # No per-widget override: the global rule already styles the progress bar,
        # and the override used a different radius (4px against the control's 10px),
        # which is exactly the inconsistency the user spotted.

    # ------------------------------------------------------------------
    # window backdrop
    # ------------------------------------------------------------------
    def showEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        # DWM needs a real window handle, which only exists once shown.
        self._apply_system_backdrop()
        self._play_entrance_once()

    def _play_entrance_once(self) -> None:
        """Run the arrival on the first show only.

        A window that re-animates every time it is restored from the taskbar would be a
        nuisance, and ``showEvent`` fires again on every restore.
        """
        if self.entrance is not None:
            return
        self.play_entrance()

    def _apply_system_backdrop(self) -> str:
        """Use the Windows 11 blurred backdrop when it is available.

        Returns the outcome ("acrylic", "unsupported platform", ...) and records it
        in :attr:`backdrop_kind` so it can be inspected in tests.  Only when the
        OS accepts the effect does the aurora become translucent - otherwise the
        window keeps painting its own opaque gradient, so the app looks identical
        on platforms without the effect rather than showing a transparent hole.
        """
        kind = theme.apply_windows_backdrop(self)
        self.backdrop_kind = kind
        translucent = kind == "acrylic"
        if translucent:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            # Keep the rounded corners the acrylic backdrop expects.
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            theme.enable_rounded_corners(self)
        self.aurora.set_opaque(not translucent)
        return kind

    # ------------------------------------------------------------------
    # translation
    # ------------------------------------------------------------------
    def _bind(self, widget: Any, text_key: str, attribute: str = "text") -> None:
        """Register ``widget`` for retranslation."""
        self._retranslate.append((widget, text_key, attribute))
        self._set_text(widget, text_key, attribute)

    def _set_text(self, widget: Any, text_key: str, attribute: str) -> None:
        value = tr(text_key, self.lang)
        if attribute == "text":
            widget.setText(value)
        elif attribute == "title":
            widget.setTitle(value)
        elif attribute == "placeholder":
            widget.setPlaceholderText(value)
        elif attribute == "tooltip":
            widget.setToolTip(value)
        elif attribute == "windowTitle":
            widget.setWindowTitle(value)

    def set_language(self, lang: str) -> None:
        """Retranslate the whole window in place (no rebuild, no restart)."""
        self.lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE

        for widget, text_key, attribute in self._retranslate:
            try:
                self._set_text(widget, text_key, attribute)
            except RuntimeError:  # pragma: no cover - widget already destroyed
                continue

        # table headers
        self.file_table.setHorizontalHeaderLabels(
            [
                tr("column_file", self.lang),
                tr("column_type", self.lang),
                tr("column_size", self.lang),
                tr("column_status", self.lang),
            ]
        )
        # Redraw the translated cells from the cache, in slices.  Deliberately NOT
        # _refresh_row() per row: that re-``stat``s every file and cost ~1.5 s for
        # 3000 files.  Only the mode can change which files are "usable", and a mode
        # change re-marks the rows itself.
        self._relabel_rows_chunked(range(len(self._row_facts)))

        index = self.language_combo.findData(self.lang)
        if index >= 0 and self.language_combo.currentIndex() != index:
            blocked = self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(index)
            self.language_combo.blockSignals(blocked)

        self.setWindowTitle(tr("app_title", self.lang))
        self._refresh_results_text()
        self._refresh_file_count()
        self._flush_repaint()

    def _flush_repaint(self) -> None:
        """Repaint the surfaces now, so no label keeps its previous text.

        Regression: switching the language left ghosted copies of the old words on screen
        until something else forced a repaint - clicking the window cleared them.  The cause
        is that retranslation only calls ``setText`` on each label, which *schedules* an
        update; the new text is drawn, but nothing guarantees the pixels the old text
        occupied are painted in the same pass.

        That matters here because of the Windows backdrop: with the DWM acrylic effect the
        window is ``WA_TranslucentBackground`` + ``WA_NoSystemBackground``, so Qt never fills
        the area behind the widgets.  Whatever the widgets do not paint stays as it was, and
        a long string replaced by a shorter one leaves the tail of the old one behind.

        So the backdrop and every glass surface are repainted explicitly, after settling the
        layout.  Repainting the window alone is not enough - measured: ``self.repaint()``
        produced no paint event on the backdrop at all, because Qt repaints a child only when
        the child itself asked to.  The set is small (the backdrop, the header, the three step
        cards, the results panel), so painting each directly is cheap and leaves nothing to
        chance.
        """
        layout = self.layout()
        if layout is not None:
            layout.activate()
        try:
            # Guarded because a test replaces ``gui.QApplication`` with a stub that has no
            # ``processEvents``.  This call only settles what the retranslation queued; the
            # repaints below are the part that matters.
            pump = getattr(QApplication, "processEvents", None)
            if callable(pump):
                pump()
            for surface in (self.aurora, *self._surfaces()):
                try:
                    surface.repaint()
                except RuntimeError:  # pragma: no cover - widget already destroyed
                    continue
            self.repaint()
        except RuntimeError:  # pragma: no cover - window already destroyed
            return

    def _on_language_changed(self) -> None:
        self.set_language(self.language_combo.currentData() or DEFAULT_LANGUAGE)

    # ------------------------------------------------------------------
    # file list
    # ------------------------------------------------------------------
    def add_paths(self, paths: Sequence[Path] | Iterable[Path]) -> None:
        """Add files or folders to the list (the public entry point for tests).

        Folder entries are kept as-is and expanded lazily, so toggling "include
        sub-folders" re-expands them consistently instead of leaving a stale
        listing behind.  Files whose extension no operation supports are still
        listed, marked *not usable*, rather than silently dropped.

        The walk and the per-file inspection run on a worker thread, so this
        returns immediately even for a folder with tens of thousands of files.  The
        table fills in as the scan proceeds; :meth:`wait_for_rows` blocks until it
        is complete (what the tests use).
        """
        incoming = ui_logic.uploaded_paths(list(paths))

        known = {ui_logic._scan_key(path) for path in self._inputs}
        for path in incoming:
            key = ui_logic._scan_key(path)
            if key in known:
                continue
            known.add(key)
            self._inputs.append(path)

        self._refresh_listing()
        self._refresh_file_count()

        for path in incoming:
            if ui_logic.looks_like_output_root(path):
                self._warn(tr("output_is_input_warning", self.lang, path=path))

    def _refresh_listing(self) -> None:
        """Re-list the inputs, honouring the recursion toggle.

        Runs on a :class:`ScanWorker`; results arrive in batches.  The table shows
        everything the picked inputs contain: an extension that does not fit the
        *current* operation stays visible but is marked *not usable* and is
        excluded when the run starts.  Hiding such rows would make the window look
        like it had lost the user's files when they switch operation.
        """
        self._cancel_scan()

        # Every listing gets a number.  A cancelled scan can still have batches
        # queued, and without this they would be appended to the *new* listing -
        # which really happened: cancelling left rows from the previous selection
        # in the table.
        self._scan_generation += 1
        generation = self._scan_generation

        # Reset what the old listing contributed.
        self._paths = []
        self._row_facts = []
        self._pending_rows = None
        self.file_table.setRowCount(0)
        self._scan_expected = 0

        worker = ScanWorker(
            self._inputs,
            recursive=self.recursive_check.isChecked(),
            mode=self._mode,
            excluded=set(self._excluded),
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.batch_ready.connect(
            lambda paths, facts, token=generation: self._on_scan_batch(token, paths, facts)
        )
        worker.finished_scan.connect(
            lambda total, error, token=generation: self._on_scan_finished(token, total, error)
        )
        self._scan_worker = worker
        self._scan_thread = thread
        thread.start()

    def _on_scan_batch(
        self, generation: int, paths: list[Path], facts: list[_FileFacts]
    ) -> None:
        """Append one batch of discovered files to the table.

        Batches from a superseded listing are dropped.
        """
        if generation != self._scan_generation:
            return
        start = len(self._paths)
        self._paths.extend(paths)
        self._row_facts.extend(facts)

        table = self.file_table
        table.setRowCount(len(self._paths))
        self._fill_rows(range(start, len(self._paths)))
        self._refresh_file_count()
        # Say what is happening: the listing of a big folder takes a moment even
        # though the window stays responsive.
        self._set_status("scanning", count=len(self._paths))

    def _on_scan_finished(self, generation: int, total: int, error: str) -> None:
        if generation != self._scan_generation:
            return
        self._scan_expected = total
        if error:
            self._warn(f"listing failed: {error}")
        if self._scan_thread is not None:
            self._scan_thread.quit()
            self._scan_thread.wait(3000)
            self._scan_thread = None
            self._scan_worker = None
        self._refresh_file_count()
        if self._status_key and self._status_key[0] == "scanning":
            self._set_status("idle")

    def _cancel_scan(self) -> None:
        """Stop an in-flight listing (the user changed the selection or settings)."""
        if self._scan_thread is not None:
            self._scan_thread.quit()
            self._scan_thread.wait(3000)
            self._scan_thread = None
            self._scan_worker = None

    def wait_for_rows(self) -> None:
        """Block until the listing is complete and every row is drawn.

        Used by tests, and by any step that needs a settled table.  Pumps the event
        loop rather than sleeping, so the scan's queued signals are delivered.
        """
        application = QApplication.instance()
        deadline = time.monotonic() + _SCAN_TIMEOUT
        while self._scan_thread is not None and time.monotonic() < deadline:
            if application is not None:
                application.processEvents()
            time.sleep(0.001)
        pending = self._pending_rows
        if pending:
            self._fill_rows(list(pending))
            self._pending_rows = None
        if self._pending_relabel:
            self._fill_rows(list(self._pending_relabel), with_name=False)
            self._pending_relabel = []

    def _fill_rows(self, rows: Iterable[int], *, with_name: bool = True) -> None:
        """Draw ``rows`` from the cached facts.

        :param with_name: also (re)create the name cell.  A language switch only
            needs the *translated* cells redrawn, and skipping the name cell means
            it does not have to re-``stat`` every file.
        """
        table = self.file_table
        for row in rows:
            path, facts = self._paths[row], self._row_facts[row]
            if with_name:
                name_item = QTableWidgetItem(path.name)
                # The columns are fixed width, so the tooltip is where the full
                # path and the exact size live.
                name_item.setToolTip(f"{path}\n{facts.size_text} ({facts.size} B)")
                table.setItem(row, 0, name_item)
            table.setItem(row, 1, QTableWidgetItem(facts.kind))
            table.setItem(row, 2, QTableWidgetItem(facts.size_text))
            status = QTableWidgetItem(self._status_for(facts.usable))
            status.setForeground(QColor(theme.TEXT_SECONDARY if facts.usable else theme.WARNING))
            table.setItem(row, 3, status)

    def _status_for(self, usable: bool) -> str:
        return tr("status_pending" if usable else "status_unusable", self.lang)

    def _relabel_rows_chunked(self, rows: Iterable[int]) -> None:
        """Redraw translated cells in slices, so a full table cannot freeze the UI.

        A language switch over 20 000 rows rewrites 60 000 cells: ~310 ms in one
        go (measured), which is a visible hitch.  Sliced, each block stays around
        10 ms and the switch feels instant.
        """
        remaining = list(rows)
        if not remaining:
            return
        self._pending_relabel = remaining
        self._relabel_next_chunk()

    def _relabel_next_chunk(self) -> None:
        remaining = self._pending_relabel
        if not remaining:
            return
        chunk = remaining[:_ROW_CHUNK]
        del remaining[:_ROW_CHUNK]
        self._fill_rows(chunk, with_name=False)
        if remaining:
            QTimer.singleShot(0, self._relabel_next_chunk)
        else:
            self._pending_relabel = []

    def _refresh_file_count(self) -> None:
        total = len(self._paths)
        allowed = _MODE_EXTENSIONS.get(self._mode, DECRYPT_EXTENSIONS)
        usable = sum(1 for path in self._paths if split_name(path)[1] in allowed)
        if total == 0:
            self.count_label.setText("")
        elif usable == total:
            self.count_label.setText(tr("count_selected", self.lang, count=total))
        else:
            self.count_label.setText(
                tr("count_mixed", self.lang, count=total, usable=usable)
            )
        # The run buttons stay enabled even when nothing fits the current
        # operation: disabling them would trap the user, because the operation
        # only changes by pressing one of them.  A run with nothing to do reports
        # "nothing to process" for the chosen operation instead.
        running = self._worker_thread is not None
        for button in (
            self.run_decrypt_button,
            self.run_encrypt_mv_button,
            self.run_encrypt_mz_button,
            self.run_restore_button,
        ):
            button.setEnabled(not running)

    # ------------------------------------------------------------------
    # interactions
    # ------------------------------------------------------------------
    def _on_add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("choose_inputs", self.lang), str(Path.home()), tr("files_filter", self.lang)
        )
        if paths:
            self.add_paths([Path(path) for path in paths])

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, tr("choose_folder", self.lang), str(Path.home())
        )
        if folder:
            self.add_paths([Path(folder)])

    def _on_remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.file_table.selectedIndexes()}, reverse=True)
        removed = [self._paths[row] for row in rows if 0 <= row < len(self._paths)]
        if not removed:
            return
        # Remember the removal so re-expanding the parent folder cannot bring the
        # row back; the picked inputs themselves are dropped when the user removes
        # one of those directly.  Keys come from ui_logic so both sides of the
        # comparison use the same cheap form (never Path.resolve() per file).
        for path in removed:
            key = ui_logic._scan_key(path)
            self._excluded.add(key)
            self._inputs = [item for item in self._inputs if ui_logic._scan_key(item) != key]
        excluded = {ui_logic._scan_key(path) for path in removed}
        self._paths = [path for path in self._paths if ui_logic._scan_key(path) not in excluded]
        self._drop_rows(excluded)
        self._refresh_file_count()

    def _drop_rows(self, excluded: set[str]) -> None:
        """Remove rows without a full re-listing (keeps the cached facts aligned)."""
        kept = [
            (path, facts)
            for path, facts in zip(self._paths, self._row_facts)
            if ui_logic._scan_key(path) not in excluded
        ]
        self._paths = [path for path, _facts in kept]
        self._row_facts = [facts for _path, facts in kept]
        self.file_table.setRowCount(len(self._paths))
        self._fill_rows(range(len(self._paths)))

    def _on_clear_files(self) -> None:
        self._cancel_scan()
        self._inputs.clear()
        self._paths.clear()
        self._row_facts.clear()
        self._excluded.clear()
        # Measured alternatives for a 20 000-row table: setRowCount(0) costs 60 ms;
        # removing the rows in chunks with processEvents in between costs 327 ms,
        # because every pass re-runs the layout.  One call is the fast path.
        self.file_table.setRowCount(0)
        self._refresh_file_count()

    def _on_recursive_toggled(self) -> None:
        self._refresh_listing()
        self._refresh_file_count()

    def _on_reset_defaults(self) -> None:
        self.advanced.reset_to_defaults()
        self.verify_check.setChecked(True)

    def header_len_value(self) -> int:
        """The header length currently typed in, or the default when unusable.

        Validation lives here because the field is a plain text input rather than a
        spin box (see :class:`AdvancedDialog`); ``build_options`` still rejects
        anything out of range for the library.
        """
        return self.advanced.header_len_value()

    def _on_advanced(self) -> None:
        """Open the hex header settings."""
        self.advanced.retranslate(self.lang)
        self.advanced.exec()

    def _on_copy_key(self) -> None:
        QGuiApplication.clipboard().setText(self.key_field.text().strip())
        self._set_status("key_detected" if self.key_field.text().strip() else "idle")

    def _on_change_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, tr("choose_output", self.lang), str(ui_logic.output_root())
        )
        if folder:
            ui_logic.OUTPUT_ROOT = Path(folder)
            self._refresh_results_text()

    def _output_target(self) -> tuple[Path, bool]:
        """Where "open the export folder" should go, and whether it had to be created.

        The last run's own folder is the interesting one, so it wins when it exists.  A
        run that has not happened yet means the export root, which is created here -
        clicking the button is a clear enough request for the folder to exist.
        """
        if self.last_run is not None and self.last_run.run_directory:
            run_directory = Path(self.last_run.run_directory)
            if run_directory.exists():
                return run_directory, False
        target = ui_logic.output_root()
        created = not target.exists()
        target.mkdir(parents=True, exist_ok=True)
        return target, created

    def _on_browse_results(self) -> None:
        """Show the export folder inside this window.

        This is the only way results are shown: asking the system's shell to open a folder
        is refused outright by a restricted session, and a window of our own needs no shell.
        """
        from .browse import BrowseDialog

        try:
            target, _created = self._output_target()
        except OSError as error:
            self._warn(tr("output_folder_unavailable", self.lang, error=str(error)))
            return

        dialog = BrowseDialog(target, self.lang, self)
        dialog.setWindowTitle(tr("browse_results", self.lang))
        dialog.exec()
        self._set_status("idle")

    def _on_copy_report(self) -> None:
        QGuiApplication.clipboard().setText(self.log_view.toPlainText())
        self._set_status("idle")

    def _on_detect_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("choose_key_file", self.lang), str(Path.home()), tr("key_filter", self.lang)
        )
        if path:
            self.detect_key_from(Path(path))

    def detect_key_from(self, path: Path) -> str | None:
        """Detect the key in ``path`` and put it in the field.

        :returns: the key, or ``None`` when detection failed (the reason is
            written to the log instead of raising)
        """
        from .key_detect import detect_key

        try:
            result = detect_key(path, header_len=self.header_len_value())
        except (DecrypterError, OSError, ValueError) as error:
            self._log(f"{tr('key_not_found', self.lang)}: {path.name} - {error}")
            self._set_status("key_not_found")
            return None

        if not result.found or not result.key:
            self._log(f"{tr('key_not_found', self.lang)}: {path.name} - {result.detail}")
            self._set_status("key_not_found")
            return None

        self.key_field.setText(result.key)
        self._log(f"{tr('key_detected', self.lang)}: {result.key}  ({result.description})")
        self._set_status("key_detected")
        if not result.confirmed:
            self._warn(tr("key_unverified", self.lang))
        return result.key

    # ------------------------------------------------------------------
    # running
    # ------------------------------------------------------------------
    def select_mode(self, mode: str, version: RpgMakerVersion | None = None) -> None:
        """Set the active operation (``decrypt`` / ``encrypt`` / ``restore``).

        ``version`` only matters for ``encrypt``: it decides MV (``.rpgmvp``) or MZ
        (``.png_``) extension naming, and therefore which files count as usable.
        """
        self._mode = mode if mode in _MODE_EXTENSIONS else "decrypt"
        if version is not None:
            self._version = version
        # Only the *usable* flag depends on the operation, and the extension is
        # already cached, so re-mark the rows instead of re-walking the disk.
        self._recompute_usable()
        self._refresh_file_count()

    def _recompute_usable(self) -> None:
        """Re-derive "usable" from the cached extensions after a mode change."""
        allowed = _MODE_EXTENSIONS.get(self._mode, DECRYPT_EXTENSIONS)
        changed = False
        for index, facts in enumerate(self._row_facts):
            usable = facts.extension in allowed
            if usable != facts.usable:
                self._row_facts[index] = replace(facts, usable=usable)
                changed = True
        if changed:
            self._fill_rows(range(len(self._row_facts)))

    def _collect_request(
        self, mode: str, version: RpgMakerVersion | None = None
    ) -> BatchRequest | str:
        """Build a :class:`BatchRequest`, or return an error message."""
        if not self._paths:
            return tr("nothing_to_do", self.lang)

        version_override = version if mode == "encrypt" else None

        if mode == "restore":
            options, error = ui_logic.build_options(
                verify_fake_header=True,
                header_len=self.header_len_value(),
                signature=DEFAULT_SIGNATURE,
                version=DEFAULT_VERSION,
                remain=DEFAULT_REMAIN,
                rpgmaker=RpgMakerVersion.MV.value,
                recursive=self.recursive_check.isChecked(),
            )
            key = None
        else:
            options, error = ui_logic.build_options(
                verify_fake_header=self.verify_check.isChecked(),
                header_len=self.header_len_value(),
                signature=self.signature_input.text(),
                version=self.version_input.text(),
                remain=self.remain_input.text(),
                rpgmaker=(version_override or RpgMakerVersion.MV).value,
                version_override=version_override,
                recursive=self.recursive_check.isChecked(),
            )
            key = None
            if not error:
                key, error = ui_logic.validate_key(
                    self.key_field.text(), options.header_len if options else DEFAULT_HEADER_LEN
                )

        if error or options is None:
            return error or "invalid settings"

        return BatchRequest(
            mode=mode,
            inputs=list(self._paths),
            key=key,
            options=options,
            package_zip=self.package_zip_check.isChecked(),
            version_override=version_override,
        )

    def run_now(
        self,
        mode: str,
        paths: Sequence[Path] | None = None,
        *,
        package_zip: bool | None = None,
        version: RpgMakerVersion | None = None,
    ) -> RunResult:
        """Run a batch **synchronously** and return its result.

        This is what the tests drive and what the buttons ultimately execute (they
        just move it to a worker thread).

        :param mode: ``"decrypt"``, ``"encrypt"`` or ``"restore"``
        :param paths: replace the file list before running
        :param package_zip: override the ZIP checkbox
        :param version: for ``"encrypt"``, which engine naming to use (default MV)
        """
        if paths is not None:
            self._cancel_scan()
            self._paths = list(paths)
            self._row_facts = [
                gui_inspect(path, _MODE_EXTENSIONS.get(mode, DECRYPT_EXTENSIONS))
                for path in self._paths
            ]
            self.file_table.setRowCount(len(self._paths))
            self._fill_rows(range(len(self._paths)))
        else:
            # The listing runs on a worker thread, so a run started immediately
            # after add_paths() would otherwise see an empty file list and report
            # "nothing to process" for files that are right there (reproduced).
            self.wait_for_rows()
        self.select_mode(mode)
        if package_zip is not None:
            self.package_zip_check.setChecked(bool(package_zip))

        request = self._collect_request(mode, version)
        if isinstance(request, str):
            self._set_status("not_started", error=request)
            self._log(tr("not_started", self.lang, error=request))
            return RunResult(result=ui_logic.RestoreResult(), run_directory=Path(), error=request)

        runner = BatchRunner(
            ProgressReport(
                on_start=self._on_progress_start,
                on_progress=self._on_progress_step,
                should_stop=self._stop_event.is_set,
            )
        )
        outcome = runner.run(request)
        self._apply_run_result(mode, outcome)
        return outcome

    def _start_run(self, mode: str, version: RpgMakerVersion | None = None) -> None:
        """Button entry point: build the request and run it on a worker thread."""
        if self._worker_thread is not None:
            return
        # Remember the operation the user chose: the table's "usable" marking, the
        # button enabling and Ctrl+R all key off self._mode, so a run started from
        # a button must update it.  Without this, picking a folder of plain .png
        # files leaves every button disabled (nothing is "usable" for decrypt) and
        # encrypting is unreachable from the window.
        self.select_mode(mode, version)
        # A listing still running would keep appending rows while the run writes
        # into them; settle it first (it is bounded and already mostly done).
        self.wait_for_rows()
        request = self._collect_request(mode, version)
        if isinstance(request, str):
            self._set_status("not_started", error=request)
            return

        self._stop_event.clear()
        self._set_running(True)
        self.progress_bar.setValue(0)
        self._set_status("working", done=0, total=len(request.inputs), name="")

        thread = QThread(self)
        worker = RunWorker(request, self._stop_event)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.started_run.connect(self._on_progress_start)
        worker.progressed.connect(self._on_progress_step)
        worker.finished_run.connect(lambda outcome: self._on_worker_finished(mode, outcome))
        self._worker_thread = thread
        self._worker = worker
        thread.start()

    def _on_worker_finished(self, mode: str, outcome: RunResult) -> None:
        self._apply_run_result(mode, outcome)
        self._set_running(False)
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait(3000)
            self._worker_thread = None
            self._worker = None
        self._refresh_file_count()

    def _on_cancel(self) -> None:
        self._stop_event.set()
        self._set_status("cancelled")
        self.cancel_button.setEnabled(False)

    def _set_running(self, running: bool) -> None:
        self.cancel_button.setEnabled(running)
        for button in (
            self.run_decrypt_button,
            self.run_encrypt_mv_button,
            self.run_encrypt_mz_button,
            self.run_restore_button,
            self.add_files_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
            self.detect_button,
        ):
            button.setEnabled(not running)
        if not running:
            self._refresh_file_count()

    # ------------------------------------------------------------------
    # progress + results
    # ------------------------------------------------------------------
    def _on_progress_start(self, total: int) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(0)

    def _on_progress_step(self, done: int, total: int, name: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(done)
        self._set_status("working", done=done, total=total, name=name)

    def _apply_run_result(self, mode: str, outcome: RunResult) -> None:
        self.last_run = outcome
        self._update_row_statuses(outcome)

        if outcome.nothing_to_do:
            # Nothing was wrong - there was simply nothing this operation could
            # handle.  Say that instead of prefixing it with "Failed".
            if outcome.skipped_already_done:
                self._set_status("all_already_done")
            else:
                self._set_status(
                    "nothing_to_process_hint",
                    extensions=self._extension_hint(mode),
                )
            if outcome.error:
                self._log(outcome.error)
        elif outcome.error and not outcome.result.outcomes and not outcome.run_directory.parts:
            # The run never got going (unreadable input, bad settings).  Note
            # ``Path().parts`` is empty, whereas ``bool(Path())`` is True.
            self._set_status("not_started", error=outcome.error)
            self._log(tr("not_started", self.lang, error=outcome.error))
        elif outcome.error and not outcome.result.outcomes:
            self._set_status("failed", error=outcome.error)
            self._log(tr("failed", self.lang, error=outcome.error))
        elif outcome.cancelled:
            self._set_status("cancelled")
        elif outcome.result.succeeded:
            self._set_status(
                "finished_ok" if not outcome.result.failed else "finished_with_errors",
                ok=len(outcome.result.succeeded),
                skipped=len(outcome.result.skipped),
                failed=len(outcome.result.failed),
            )
        elif outcome.result.failed:
            # Every file failed.  Saying "nothing to process" here would bury the
            # failure behind a reassurance, so report it as the failure it is.
            # The concrete reason per file is written by _write_report below, which
            # replaces the log, so it must not be appended here.
            self._set_status(
                "finished_with_errors",
                ok=0,
                skipped=len(outcome.result.skipped),
                failed=len(outcome.result.failed),
            )
        elif outcome.skipped_already_done and not outcome.unprocessable:
            self._set_status("all_already_done")
        else:
            self._set_status("nothing_to_do")

        self._write_report(mode, outcome)
        self._refresh_results_text()

    def _extension_hint(self, mode: str) -> str:
        """The extensions the active operation accepts, for a status message."""
        allowed = _MODE_EXTENSIONS.get(mode, DECRYPT_EXTENSIONS)
        return " ".join(f".{extension}" for extension in sorted(allowed))

    def _update_row_statuses(self, outcome: RunResult) -> None:
        """Mark the rows of the files this run touched.

        Outcomes are reported for the *staged copies* (``<stage>/<job>/input/
        0001/<name>``), because that is what the library is pointed at, while the
        rows hold the original paths.  ``stage_files`` preserves file names, so
        the name is the reliable join key - and it is also what the table shows.
        """
        # The rows must exist before they can be re-marked.
        self.wait_for_rows()

        by_name: dict[str, tuple[str, str, str]] = {}
        for item in outcome.result.outcomes:
            if item.ok:
                text, colour = tr("status_ok", self.lang), theme.SUCCESS
            elif item.skipped:
                text, colour = tr("status_skipped", self.lang), theme.TEXT_MUTED
            else:
                text, colour = tr("status_failed", self.lang), theme.DANGER
            detail = str(item.destination) if item.ok and item.destination else ""
            by_name[item.source.name] = (text, colour, detail)

        for row, path in enumerate(self._paths):
            entry = by_name.get(path.name)
            if entry is None:
                continue
            text, colour, detail = entry
            item = QTableWidgetItem(text)
            item.setForeground(QColor(colour))
            if detail:
                item.setToolTip(detail)
            self.file_table.setItem(row, 3, item)

    def _write_report(self, mode: str, outcome: RunResult) -> None:
        lines = [tr("report_header", self.lang), ""]
        lines.append(f"{tr('step_run', self.lang)}: {mode}")
        # Same trap as below: Path() is truthy, so check for real parts.
        if outcome.run_directory.parts:
            lines.append(tr("exported_to", self.lang, path=outcome.run_directory))
        if outcome.archive:
            lines.append(f"ZIP: {outcome.archive}")
        lines.append("")
        for item in outcome.result.outcomes:
            if item.ok:
                marker = tr("status_ok", self.lang)
            elif item.skipped:
                marker = tr("status_skipped", self.lang)
            else:
                marker = tr("status_failed", self.lang)
            if item.ok:
                # The run folder is named on its own line above, so the per-file
                # line stays short and readable: name, size, done.
                detail = (
                    f"{item.output_name}  ({format_size(item.size)})"
                    if item.destination
                    else item.output_name
                )
            else:
                detail = str(item.error) if item.error else item.reason
            lines.append(f"[{marker}] {item.source.name} -> {detail}")

        if outcome.unprocessable:
            lines.append("")
            lines.append(f"{tr('status_unusable', self.lang)}: " + ", ".join(p.name for p in outcome.unprocessable))
        for problem in outcome.problems:
            lines.append(f"! {problem}")
        if outcome.cancelled:
            lines.append("")
            lines.append(tr("cancelled", self.lang))
        if outcome.error:
            lines.append("")
            lines.append(tr("failed", self.lang, error=outcome.error))

        text = "\n".join(lines)
        self.log_view.setPlainText(text)

        # ``Path()`` is truthy, so an empty run_directory must be tested by its
        # parts: otherwise a run that never started writes ``./_logs/report.txt``
        # into whatever the current directory happens to be (it did, once, into the
        # project root), and the report claims results were exported to ".".
        if not outcome.run_directory.parts:
            return
        try:
            logs = outcome.run_directory / "_logs"
            logs.mkdir(parents=True, exist_ok=True)
            (logs / "report.txt").write_text(text, encoding="utf-8")
        except OSError:
            pass

    def _refresh_results_text(self) -> None:
        """Show where results will actually go.

        The path comes from the resolver rather than the module constant, so a packaged
        build that had to move its output somewhere writable shows the real folder.  A user
        who cannot find their files because the interface named the wrong directory is a
        worse failure than a slightly longer label.
        """
        try:
            root = ui_logic.output_root()
        except OSError:  # pragma: no cover - defensive; the resolver has its own fallbacks
            root = ui_logic.OUTPUT_ROOT
        self.output_root_label.setText(f"{tr('output_root_label', self.lang)}: {root}")
        self._announce_relocation_once(root)
        self._refresh_status()

    def _announce_relocation_once(self, root: Path) -> None:
        """Say so, once, when results are not going where the interface implies.

        Only relevant to a packaged build unzipped somewhere read-only: the folder moves
        into the user's profile, and nothing else in the window would reveal that.  Said
        once, so the log does not fill up with the same sentence on every status change.
        """
        if self._relocation_announced:
            return
        self._relocation_announced = True
        expected = ui_logic.install_root() / "output"
        if root == expected:
            return
        self._log(tr("output_relocated", self.lang, path=str(root)))

    def _set_status(self, text_key: str, **values: Any) -> None:
        changed = self._status_key != (text_key, values)
        self._status_key = (text_key, values)
        self._refresh_status()
        if changed:
            self._flash_status()

    def _flash_status(self) -> None:
        """Light the status line briefly when it changes.

        The status text is small and sits beside a long progress bar, so a change is easy
        to miss.  Flashing it is not decoration: it is what makes the state change
        noticeable at the moment it happens.  The colour is interpolated through the
        accent and back, which a stylesheet can express and a graphics effect cannot do
        without going stale - the reason nothing in this interface uses one.
        """
        if not motion.motion_enabled():
            self.status_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent;")
            return
        animation = motion.Animation(self._on_status_flash, duration=motion.DURATION_SLOW, parent=self)
        animation.start()
        self._status_animation = animation

    def _on_status_flash(self, value: float) -> None:
        # Up quickly, back down slowly: the peak lands at ~25% of the animation, so the
        # change registers immediately and the colour then settles out of the way.
        peak = 1.0 - abs(value * 2.0 - 0.5) * 2.0 if value < 0.5 else 1.0 - (value - 0.5) * 2.0
        strength = min(max(peak, 0.0), 1.0)
        colour = _mix_colour(theme.TEXT_SECONDARY, theme.ACCENT_LIGHT, strength)
        self.status_label.setStyleSheet(f"color: {colour}; background: transparent;")

    def _refresh_status(self) -> None:
        if self._status_key is None:
            self.status_label.setText(tr("idle", self.lang))
            return
        text_key, values = self._status_key
        try:
            self.status_label.setText(tr(text_key, self.lang, **values))
        except KeyError:  # pragma: no cover - defensive
            self.status_label.setText(text_key)

    def _log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _warn(self, message: str) -> None:
        self._log(f"! {message}")

    # ------------------------------------------------------------------
    # window level drag & drop
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.add_paths(paths)
        event.acceptProposedAction()

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        self._stop_event.set()
        self._cancel_scan()
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait(3000)
        super().closeEvent(event)


def _bind_all(window: MainWindow) -> None:
    """Wire every static label through :meth:`MainWindow._bind`.

    Kept outside ``_build_ui`` so the construction code stays readable.
    """
    bindings: list[tuple[Any, str, str]] = [
        (window.key_card.title_label, "step_key", "text"),
        (window.files_card.title_label, "step_files", "text"),
        (window.options_card.title_label, "step_run", "text"),
        (window.title_label, "app_title", "text"),
        (window.subtitle_label, "app_subtitle", "text"),
        (window.language_label, "language", "text"),
        (window.key_label, "key_label", "text"),
        (window.key_field, "key_placeholder", "placeholder"),
        (window.key_hint, "key_hint", "text"),
        (window.key_source_label, "key_source_label", "text"),
        (window.detect_button, "detect_key", "text"),
        (window.copy_key_button, "copy_key", "text"),
        (window.clear_key_button, "clear_key", "text"),
        (window.add_files_button, "add_files", "text"),
        (window.add_folder_button, "add_folder", "text"),
        (window.remove_button, "remove_selected", "text"),
        (window.clear_button, "clear_list", "text"),
        (window.drop_hint, "drag_hint", "text"),
        (window.verify_check, "verify_header", "text"),
        (window.verify_hint, "verify_header_hint", "text"),
        (window.advanced_button, "advanced", "text"),
        (window.recursive_check, "recursive", "text"),
        (window.package_zip_check, "package_zip", "text"),
        (window.zip_hint, "package_zip_hint", "text"),
        (window.run_decrypt_button, "run_decrypt", "text"),
        (window.run_encrypt_mv_button, "run_encrypt_mv", "text"),
        (window.run_encrypt_mz_button, "run_encrypt_mz", "text"),
        (window.run_restore_button, "run_restore", "text"),
        (window.cancel_button, "cancel", "text"),
        (window.browse_results_button, "browse_results", "text"),
        (window.browse_results_button, "browse_results_tip", "tooltip"),
        (window.copy_report_button, "copy_report", "text"),
        (window.results_label, "step_results", "text"),
        (window.change_output_button, "change_output", "text"),
    ]
    for widget, text_key, attribute in bindings:
        window._bind(widget, text_key, attribute)


def project_icon() -> QIcon:
    """The application icon, from the generated logo files.

    Loaded from the package's own ``assets`` directory so it is found however the code
    is imported - and returning an empty :class:`QIcon` rather than raising when the
    files are absent, because a missing icon must not stop the tool from starting.
    (``assets`` is authored by ``tools/make_logo.py`` and checked by
    ``tools/check_logo.py``.)
    """
    directory = Path(__file__).resolve().parent / "assets"
    icon = QIcon()
    # The .ico carries Windows' small sizes; the PNGs cover everything else and make
    # the icon work on a platform that cannot read .ico.
    for name in ("logo.ico", "logo-256.png", "logo-64.png", "logo-32.png", "logo-16.png"):
        path = directory / name
        if path.exists():
            icon.addFile(str(path))
    return icon


def apply_project_icon(target: Any, icon: QIcon) -> None:
    """Give ``target`` the project icon, tolerating a stand-in without the method.

    The entry point is testable with a stub ``QApplication``, and the icon is
    decoration: a target that cannot take one must not stop the window from opening.
    """
    setter = getattr(target, "setWindowIcon", None)
    if setter is None or icon.isNull():
        return
    setter(icon)


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m rpgmv_decrypter.gui`` entry point."""
    raw = list(sys.argv[1:] if argv is None else argv)

    # ``--cli [args...]`` hands the rest to the command line interface.  This exists for
    # the packaged build: it ships one executable, the folder has no Python on PATH, so
    # the documented ``python -m rpgmv_decrypter.cli`` cannot be typed there - and the
    # launcher beside the executable forwards to this flag instead.
    if raw and raw[0] == "--cli":
        from .cli import main as cli_main

        return cli_main(raw[1:])

    parser = argparse.ArgumentParser(
        prog="python -m rpgmv_decrypter.gui",
        description="Desktop interface for the RPG Maker MV/MZ decrypter.",
    )
    parser.add_argument(
        "--lang",
        choices=sorted(LANGUAGES),
        default=DEFAULT_LANGUAGE,
        help="interface language: zh (default) or en; switchable in the window",
    )
    arguments = parser.parse_args(raw)

    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName(tr("app_title", arguments.lang))
    icon = project_icon()
    apply_project_icon(application, icon)

    window = MainWindow(arguments.lang)
    window.set_language(arguments.lang)
    apply_project_icon(window, icon)
    window.show()

    # A self-test entry point, used by tools/check_gui_starts.py: build the window,
    # report that it succeeded, and leave.  Without it, checking the *packaged*
    # executable would mean starting a windowed process and killing it, which cannot
    # tell "opened fine" from "hung on startup".
    if os.environ.get("RPGMV_GUI_SELFTEST"):
        application.processEvents()
        print(f"window ready: {window.width()}x{window.height()} lang={window.lang}")
        return 0

    # A second self-test for the results browser: it is a separate window with its own
    # imports, so "the main window opens" says nothing about whether it does.
    if os.environ.get("RPGMV_GUI_SELFTEST_BROWSE"):
        from .browse import BrowseDialog

        try:
            target, _created = window._output_target()
        except OSError as error:
            print(f"browse self-test could not resolve a folder: {error}")
            return 1
        dialog = BrowseDialog(target, window.lang, window)
        dialog.show()
        application.processEvents()
        print(
            f"browse ready: {dialog.table.rowCount()} rows, "
            f"folder={dialog.current}, title={dialog.title.text()!r}"
        )
        return 0

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
