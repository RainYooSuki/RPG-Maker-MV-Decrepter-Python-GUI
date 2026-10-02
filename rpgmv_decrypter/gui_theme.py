"""Visual theme: Apple-style "Liquid Glass" material on a solid dark backdrop.

The reference is Apple's Liquid Glass (WWDC 2025): translucent material whose
identity comes from **optics** rather than from colour -

* a crisp specular highlight along the lit top edge, fading around the sides,
* a soft inner glow just inside that edge, so the surface reads as having depth,
* a mostly-transparent fill that lets the surface behind tint it,
* large continuous corner radii, and soft layered shadows for elevation,
* high-contrast light labels on near-black material (the reference measures
  ~20:1 for body text).

The window sits on a dark, palette-tinted background (:data:`BACKDROP_BASE` with the
light fields in :data:`AURORA_FIELDS`) because the interface has to stay readable, and
a flat one would leave the glass nothing to transmit.  That also makes the palette
measurable: ``tools/tune_liquid_glass.py`` sweeps backdrop greys and glass lifts and
reports the contrast of every text colour on both the bare background and a glass
panel, and ``tools/tune_backdrop_palette.py`` searches the field weights against the
two constraints that pull against each other (transmission and contrast), so the
numbers in this file are fitted, not guessed.  ``tests/test_gui.py`` fails if they
regress.

What Qt cannot do: Apple's material also *refracts* what is behind it (a lensing
displacement at the edges).  That needs a per-pixel shader, which Qt widgets cannot
run, so there is none here - the glass transmits the backdrop's tone and variation and
carries the painted rim and glow, and nothing in this file claims to bend light.
"""

from __future__ import annotations

import sys
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

__all__ = [
    "ACCENT",
    "ACCENT_HOVER",
    "ACCENT_PRESSED",
    "ACCENT_TEXT",
    "AURORA_FIELDS",
    "BACKDROP_BASE",
    "BACKDROP_BOTTOM_ALPHA",
    "BACKDROP_DEEP",
    "DANGER",
    "GLASS_BORDER",
    "GLASS_BORDER_SOFT",
    "GLASS_EDGE",
    "GLASS_FILL",
    "GLASS_FILL_STRONG",
    "GLASS_FILL_SUNKEN",
    "GLASS_LIFT",
    "GLASS_TOP_LIFT",
    "RADIUS_LG",
    "RADIUS_MD",
    "RADIUS_CAPSULE",
    "RADIUS_SM",
    "SPACE_LG",
    "SPACE_MD",
    "SPACE_SM",
    "SPACE_XS",
    "SUCCESS",
    "TEXT_MUTED",
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "WARNING",
    "apply_windows_backdrop",
    "glass_style",
    "mono_font",
    "pick_font",
    "shadow",
    "type_scale",
    "ui_font",
]

# ----------------------------------------------------------------------
# palette - fitted by tools/tune_liquid_glass.py, guarded by the tests
# ----------------------------------------------------------------------
#: The window's base fill: a dark grey, dark enough for light text at AAA.
BACKDROP_BASE = "#1c1c1e"

#: The vertical gradient's ends.  A dark-but-not-flat background is what gives the
#: glass something to transmit; see :func:`paint_backdrop`.
BACKDROP_SHEEN = "#2b2b31"
BACKDROP_SHEEN_ALPHA = 190
BACKDROP_DEEP = "#131316"
BACKDROP_BOTTOM_ALPHA = 210

#: Large soft light fields over the gradient, as
#: ``(x fraction, y fraction, radius fraction, colour, alpha)``.
#:
#: These are what the panels actually show through themselves.  With a flat backdrop
#: the inside of a card varied by one luma level across its entire width - the glass
#: was transmitting faithfully and there was nothing to transmit - which is why the
#: material read as a painted rectangle.
#:
#: Toned to the user's palette so the background and the accent belong to one family:
#: the upper left and the bottom take the mid blue, the right takes the periwinkle and
#: the violet.
#:
#: The weights were searched by ``tools/tune_backdrop_palette.py``, because two
#: constraints pull against each other.  A stronger tint reads as more deliberate, but
#: it also **flattens** the background (the fields converge on their own colour), which
#: weakens what the glass has to transmit *and* lifts the cards until the muted hint
#: text loses its WCAG AA margin - measured at 4.11:1 for the heaviest set that the
#: first search called acceptable.  These weights keep the muted text near 4.7:1 on the
#: brightest card surface while still transmitting the tone.
AURORA_FIELDS: tuple[tuple[float, float, float, str, int], ...] = (
    (0.18, 0.06, 0.62, "#2f4675", 108),  # mid blue, upper left
    (0.86, 0.30, 0.55, "#4b5280", 88),   # periwinkle, right
    (0.45, 0.98, 0.70, "#1d3a58", 96),   # deep blue, bottom
    (0.68, 0.72, 0.40, "#413a5e", 66),   # violet, low right
)
BACKDROP_VIGNETTE_ALPHA = 70

TEXT_PRIMARY = "#f5f5f7"
TEXT_SECONDARY = "#d4d4da"
#: Hint text.  Chosen for margin, not for the minimum, and re-checked whenever the
#: glass changes: at #a1a1a8 it measured 4.49:1 against the lit part of a card, and at
#: #b0b0b8 it still came out 4.47:1 on the brightest surface a hint actually sits on.
#: #b8b8c0 clears 4.5:1 everywhere (including the lit rim) while staying clearly
#: dimmer than the secondary label.  Guarded by tests/test_gui.py,
#: verification/h_gui_regressions.py and tools/tune_liquid_glass.py.
TEXT_MUTED = "#c4c4cc"

# ----------------------------------------------------------------------
# accent - the user's blue/violet palette
# ----------------------------------------------------------------------
#: ``#1E3663`` (the darkest swatch) for the primary action.  It is deep enough that a
#: **white** label stays well clear of WCAG AA - which matters, because white-on-blue is
#: the classic accessibility trap this palette invites.
ACCENT = "#1e3663"
#: Hover and press move *lighter* through the palette rather than darker: at this depth
#: a darker fill would lose the label, and the family's lighter blues are the natural
#: "raised" states.  Both are measured against the white label by the tests.
ACCENT_HOVER = "#2f4f88"
ACCENT_PRESSED = "#16294b"
ACCENT_TEXT = "#ffffff"

#: The palette's lighter blues, for surfaces that need to feel tinted without carrying
#: text on top of them.
ACCENT_SOFT = "#5d76ba"
ACCENT_LIGHT = "#bdd8ff"
ACCENT_VIOLET = "#a7a7d1"
ACCENT_SKY = "#3d91cc"

SUCCESS = "#30d158"
WARNING = "#ffd60a"
DANGER = "#ff453a"

# ----------------------------------------------------------------------
# glass - alpha numbers, all <= the largest lift that keeps text readable
# ----------------------------------------------------------------------
#: How much white light the material's *body* adds to what is behind it.  Kept low
#: on purpose: the identity of the material comes from the specular rim and the
#: inner glow (see ``gui.paint_glass_edges``), not from an overall lift, and every
#: extra point of lift costs text contrast on the panel.  Fitted by
#: ``tools/tune_liquid_glass.py`` and guarded by ``tests/test_gui.py``.
GLASS_LIFT = 26

#: Panel fill, as rgba over the window.  The alpha *is* the lift.
GLASS_FILL = f"rgba(255, 255, 255, {GLASS_LIFT})"
GLASS_FILL_STRONG = "rgba(255, 255, 255, 42)"
#: Inputs and tables are *inset*: darker than the window, so they read as wells.
GLASS_FILL_SUNKEN = "rgba(0, 0, 0, 90)"

#: Extra alpha on the lit top edge of a panel.  A *thin* rim, not a wash: the lit zone
#: used to run to 35% of the card, which made the top third ~10 points lighter than the
#: middle - and that is the zone the first label and field sit in, so the muted text
#: lost its WCAG AA margin there.
GLASS_TOP_LIFT = 6
#: How far down the lit edge reaches, as a fraction of the panel's height.
GLASS_TOP_STOP = 0.08
#: How much the panel fades towards its bottom edge.
GLASS_BOTTOM_FADE = 16

# ----------------------------------------------------------------------
#: The specular edge: near-white on the lit side, fading to a faint hairline.
GLASS_EDGE = "rgba(255, 255, 255, 128)"
GLASS_EDGE_SOFT = "rgba(255, 255, 255, 48)"
GLASS_BORDER = "rgba(255, 255, 255, 60)"
GLASS_BORDER_SOFT = "rgba(255, 255, 255, 34)"
#: The inner glow just inside the top edge, painted by glass_edge_style().
GLASS_INNER_GLOW = "rgba(255, 255, 255, 26)"

#: How much brighter the rim and inner glow get when the pointer is over an
#: interactive panel.  Small on purpose: the highlight has to be visible without
#: lifting the surface the text sits on, which tests/test_gui.py measures.
HOVER_LIFT = 1.7

# ----------------------------------------------------------------------
# metrics - one scale, used everywhere
# ----------------------------------------------------------------------
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 14
SPACE_LG = 22

#: Apple's continuous-corner look means generous radii.
RADIUS_SM = 10
RADIUS_MD = 14
RADIUS_LG = 22
#: Radius for capsule controls (buttons, switch tracks, scrollbar handles).
#:
#: **Not** a huge sentinel.  The idiom of using a very large value so Qt clamps it to
#: half the height does *not* work in a stylesheet: measured against the rendered
#: window, ``border-radius: 980px`` draws **no rounding at all** - a square corner -
#: while 21px gives a perfect capsule and 16px/10px give a curve.  Qt accepts a large
#: radius only up to a point and then drops it.  The user saw the result ("怎么还有
#: 直角").  14px is within every honoured value and visibly rounded on the 30-43px
#: controls this is used on; tests/test_gui.py measures the corner curvature of a
#: real button so a sentinel cannot creep back in.
RADIUS_CAPSULE = 14

#: Accepted ``border-radius`` values, in pixels.  Anything drawn in this interface
#: must use one of these, or a sharply rounded corner appears next to a gentle one
#: and the material stops reading as a single surface - the user spotted exactly
#: that ("圆角直角是不统一的").  Scrollbar handles are caps, hence RADIUS_CAPSULE.
#: ``tests/test_gui.py`` scans every stylesheet in the app for other values.
RADIUS_TOKENS = (RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_CAPSULE)
#: The radius for a bordered control: fields, wells, the table, the log.
CONTROL_RADIUS = RADIUS_SM


#: The same colours as the ``rgba(...)`` strings above, as ``QColor``-usable tuples.
#: ``QColor("rgba(0, 0, 0, 90)")`` is **invalid** - Qt's QColor does not parse CSS
#: colour syntax - and passing it paints nothing at all.  Anything painted with
#: QPainter (the switch, the glass edges) must use these instead.  Checked by
#: tests/test_gui.py.
SUNKEN_RGBA = (0, 0, 0, 90)
BORDER_RGBA = (255, 255, 255, 60)
EDGE_RGBA = (255, 255, 255, 128)


def qcolor(rgba: tuple[int, int, int, int]) -> QColor:
    """A :class:`QColor` from an ``(r, g, b, a)`` tuple.

    Use this rather than ``QColor(string)`` for the theme's translucent colours: the
    string form of a CSS ``rgba()`` value is not understood by ``QColor`` and yields
    an *invalid* colour, which paints nothing instead of raising.
    """
    colour = QColor(*rgba)
    assert colour.isValid(), f"{rgba} did not make a valid colour"
    return colour

#: (role, point size, weight) - one type scale for the whole window.
type_scale = {
    "display": (22, QFont.Weight.DemiBold),
    "title": (15, QFont.Weight.DemiBold),
    "subtitle": (11, QFont.Weight.Normal),
    "body": (10, QFont.Weight.Normal),
    "label": (10, QFont.Weight.Medium),
    "caption": (9, QFont.Weight.Normal),
    "badge": (9, QFont.Weight.DemiBold),
    "mono": (10, QFont.Weight.Normal),
}


# ----------------------------------------------------------------------
# fonts
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def _available_families() -> set[str]:
    return set(QFontDatabase.families())


@lru_cache(maxsize=8)
def pick_font(*candidates: str) -> str:
    """First installed family from ``candidates``, else an empty string.

    Chinese text needs a family that actually has CJK glyphs, otherwise Qt falls
    back per-glyph and the line height jumps between labels.
    """
    families = _available_families()
    for name in candidates:
        if name in families:
            return name
    return ""


def ui_font(*, size_role: str = "body") -> QFont:
    """A font from the type scale, with CJK-capable families preferred."""
    size, weight = type_scale[size_role]
    family = pick_font(
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Segoe UI Variable Text",
        "Segoe UI",
        "Noto Sans CJK SC",
        "PingFang SC",
    )
    font = QFont(family) if family else QFont()
    font.setPointSize(size)
    font.setWeight(weight)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


@lru_cache(maxsize=1)
def mono_font() -> QFont:
    """Monospaced font for keys, hex values and paths."""
    size, weight = type_scale["mono"]
    family = pick_font("Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono")
    font = QFont(family) if family else QFont()
    font.setPointSize(size)
    font.setWeight(weight)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def font_size(role: str) -> int:
    return type_scale[role][0]


#: Vertical padding on an input control.  Kept modest so the control stays compact.
INPUT_PADDING_Y = 5
INPUT_PADDING_X = 10


def input_min_height(*, role: str = "body") -> int:
    """The smallest height an input may be squeezed to without clipping its text.

    This exists because a layout short of room will happily squash the flexible
    widgets - which are exactly the text inputs - and Qt does not enforce
    ``sizeHint`` for them.  The fields were being pressed from 32px to 22px, which
    sliced the glyphs in half; the numbers here come from
    ``tools/probe_field_height.py``, and every input is given this as a hard
    minimum so the floor does not depend on how much room the card has.
    """
    metrics = QFontMetrics(ui_font(size_role=role))
    return metrics.height() + 2 * INPUT_PADDING_Y + 2  # + the two border pixels


# ----------------------------------------------------------------------
# glass style
# ----------------------------------------------------------------------
def _alpha_of(rgba: str) -> int:
    """Read the alpha out of ``rgba(r, g, b, a)`` so a gradient can derive from it."""
    if rgba.startswith("rgba"):
        try:
            return int(rgba.rsplit(",", 1)[1].strip().rstrip(")"))
        except (ValueError, IndexError):
            return 30
    return 255


def glass_style(
    *,
    selector: str = "QFrame#glass",
    radius: int = RADIUS_LG,
    fill: str = GLASS_FILL,
    border: str = GLASS_BORDER_SOFT,
    lit_edge: bool = True,
) -> str:
    """Stylesheet for one Liquid Glass surface.

    The fill is a gentle vertical gradient - a touch brighter where the light lands
    on the top edge, fading as it falls - plus a hairline border.  The *specular*
    part (the bright lit edge) is added by :func:`glass_edge_style`, because Qt
    cannot vary one border's colour along its length.

    The gradient is *derived from* ``fill`` and never exceeds it by more than
    :data:`GLASS_TOP_LIFT`.  That matters: an earlier version brightened the bottom
    stop as well, which made the panel much lighter than the fitted palette and
    quietly cost the muted text its WCAG AA margin.

    ``selector`` matters: a widget that needs its own ``objectName`` (so tests can
    find it) must pass that id here, or the rule silently matches nothing and the
    surface renders as a transparent hole.  ``tests/test_gui.py`` renders each
    surface and asserts it is lighter than the backdrop, which is the check that
    catches exactly that mistake.
    """
    alpha = _alpha_of(fill)
    top = min(alpha + GLASS_TOP_LIFT, 255)
    bottom = max(alpha - GLASS_BOTTOM_FADE, 4)
    return (
        f"{selector} {{"
        f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f" stop:0 rgba(255,255,255,{top}),"
        f" stop:{GLASS_TOP_STOP} rgba(255,255,255,{alpha}),"
        f" stop:0.85 rgba(255,255,255,{alpha}),"
        f" stop:1 rgba(255,255,255,{bottom}));"
        f"border-radius: {radius}px;"
        f"border: 1px solid {border};"
        + (f"border-top: 1px solid {GLASS_EDGE};" if lit_edge else "")
        + "}"
    )


def glass_edge_style(selector: str, *, radius: int = RADIUS_LG) -> str:
    """The specular rim and inner glow that make a panel read as glass.

    Qt stylesheets give a border one flat colour, so the "light falls on the top
    edge and fades around the sides" effect is painted by the widget itself (see
    ``gui.paint_glass_edges``) using this geometry.  This function only supplies the
    radius so both agree.
    """
    return f"{selector} {{ border-radius: {radius}px; }}"


#: Drop-shadow shape.  Painted by ``gui.paint_glass_edges`` rather than set as a
#: QGraphicsDropShadowEffect - see :func:`shadow` for why.
SHADOW_SPREAD = 6
SHADOW_ALPHA = 120
SHADOW_OFFSET_Y = 3


def shadow(widget: QWidget, *, blur: int = 0, y: int = 0, alpha: int = 0) -> QWidget:
    """No-op kept for call-site compatibility; the shadow is painted instead.

    ``QGraphicsDropShadowEffect`` renders the widget into an offscreen pixmap and
    caches the blur.  On a panel that contains a ``QScrollArea`` whose children
    keep repainting (the cards scroll now), that cache goes stale and leaves copies
    of child text behind - the "伪影" the user reported.  Painting the shadow costs
    an extra few strokes and cannot go stale, so the effect is gone entirely.

    The shadow is drawn outside the panel's own outline by
    ``gui.paint_glass_edges``; a widget cannot paint beyond its own rect, so the
    glow is inset around the edge and reads as a dark vignette.
    """
    return widget


# ----------------------------------------------------------------------
# backdrop painting
# ----------------------------------------------------------------------
def paint_backdrop(widget: QWidget, painter: QPainter, *, opaque: bool = True) -> None:
    """Paint the window background the glass floats above.

    The background is **dark but not flat**: large, soft, desaturated light fields over
    a vertical gradient, in the spirit of a darkened wallpaper.

    That is not decoration - it is what makes the material glass.  Measured with a flat
    fill behind it, the inside of a card varied by **1 luma level** (53 to 54) across
    its whole width: the glass was transmitting the background faithfully, there was
    simply nothing there to transmit, so every panel read as a painted rectangle.  The
    reference the user supplied shows the opposite - wallpaper patterns are visible
    through Control Center's glass - and they were right that the material was missing.

    Readability is preserved by keeping the fields dark and the whole thing low in
    contrast; the cards still do most of the work of separating content.

    :param opaque: ``False`` paints only a scrim, used when a blurred *system*
        backdrop sits behind the window.
    """
    rect = widget.rect()
    if rect.isEmpty():
        return

    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    base = QColor(BACKDROP_BASE)
    if opaque:
        painter.fillRect(rect, base)
    else:
        scrim = QColor(base)
        scrim.setAlpha(215)
        painter.fillRect(rect, scrim)

    # A vertical gradient so the top and bottom of the window are not the same value.
    vertical = QLinearGradient(0.0, 0.0, 0.0, float(rect.height()))
    top = QColor(BACKDROP_SHEEN)
    top.setAlpha(BACKDROP_SHEEN_ALPHA if opaque else int(BACKDROP_SHEEN_ALPHA * 0.6))
    bottom = QColor(BACKDROP_DEEP)
    bottom.setAlpha(BACKDROP_BOTTOM_ALPHA if opaque else int(BACKDROP_BOTTOM_ALPHA * 0.6))
    vertical.setColorAt(0.0, top)
    vertical.setColorAt(1.0, bottom)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(vertical)
    painter.drawRect(rect)

    # Large soft light fields.  Deliberately few, wide and low in contrast: enough for
    # the glass to have something to show, not enough to compete with the interface.
    longest = max(rect.width(), rect.height())
    for x_fraction, y_fraction, radius_fraction, colour_spec, alpha in AURORA_FIELDS:
        if not opaque:
            alpha = int(alpha * 0.6)
        glow = QRadialGradient(
            QPointF(rect.width() * x_fraction, rect.height() * y_fraction),
            longest * radius_fraction,
        )
        glow_colour = QColor(colour_spec)
        glow_colour.setAlpha(alpha)
        glow.setColorAt(0.0, glow_colour)
        faded = QColor(colour_spec)
        faded.setAlpha(0)
        glow.setColorAt(1.0, faded)
        painter.setBrush(glow)
        painter.drawRect(rect)

    vignette = QRadialGradient(
        QPointF(rect.width() / 2, rect.height() / 2),
        max(rect.width(), rect.height()) * 0.8,
    )
    vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
    vignette.setColorAt(0.62, QColor(0, 0, 0, 0))
    vignette.setColorAt(1.0, QColor(0, 0, 0, BACKDROP_VIGNETTE_ALPHA))
    painter.setBrush(vignette)
    painter.drawRect(rect)
    painter.setBrush(Qt.BrushStyle.NoBrush)


# ----------------------------------------------------------------------
# Windows 11 system backdrop
# ----------------------------------------------------------------------
def apply_windows_backdrop(widget: QWidget, *, dark: bool = True) -> str:
    """Ask DWM for a blurred system backdrop behind ``widget``.

    Returns a short description of what was applied, for logging/tests.  On
    anything but Windows 11 this is a no-op ("unsupported") and the painted
    backdrop alone carries the look, so nothing breaks without it.
    """
    if sys.platform != "win32":
        return "unsupported platform"

    try:  # pragma: no cover - exercised only on Windows
        import ctypes
        from ctypes import wintypes

        dwmapi = ctypes.windll.dwmapi
        handle = int(widget.winId())

        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20, DWMWA_SYSTEMBACKDROP_TYPE = 38
        # DWMSBT_TRANSIENTWINDOW (Acrylic) = 3
        value = ctypes.c_int(1 if dark else 0)
        dark_result = dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(handle), 20, ctypes.byref(value), ctypes.sizeof(value)
        )
        backdrop = ctypes.c_int(3)
        backdrop_result = dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(handle), 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop)
        )
        if backdrop_result == 0:
            return "acrylic"
        if dark_result == 0:
            return "dark-mode-only"
        return "unsupported build"
    except Exception:  # pragma: no cover - any failure just means no blur
        return "unavailable"


def enable_rounded_corners(widget: QWidget) -> bool:
    """Ask DWM for rounded window corners (Windows 11)."""
    if sys.platform != "win32":
        return False
    try:  # pragma: no cover - Windows only
        import ctypes
        from ctypes import wintypes

        # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
        preference = ctypes.c_int(2)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(int(widget.winId())),
            33,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
        return result == 0
    except Exception:  # pragma: no cover
        return False


# ----------------------------------------------------------------------
# small composite widgets used by the panels
# ----------------------------------------------------------------------
class SectionLabel(QLabel):
    """Caption used to group controls inside a card."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFont(ui_font(size_role="label"))
        self.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)


class HintLabel(QLabel):
    """Muted helper text; wraps so long hints do not stretch the layout."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFont(ui_font(size_role="caption"))
        self.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent;")
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)


class FieldLabel(QLabel):
    """Label for an input control."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFont(ui_font(size_role="label"))
        self.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")


def labelled(control: QWidget, text: str) -> QWidget:
    """Stack a :class:`FieldLabel` above ``control`` in a tight wrapper."""
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACE_XS)
    layout.addWidget(FieldLabel(text))
    layout.addWidget(control)
    return wrapper


def group_field(label: QLabel, control: QWidget) -> QWidget:
    """Stack ``label`` above ``control`` as a single unit.

    Grouping matters for spacing: adding a label and its field as two separate
    children of the card gave both the same gap as everything else, so a label ended
    up closer to the field *above* it than to its own - the form read as one cramped
    block (measured with ``tools/dump_options_card.py``).  Inside a group the gap is
    tight; between groups the card's spacing applies.
    """
    wrapper = QWidget()
    wrapper.setObjectName("fieldGroup")
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACE_XS)
    layout.addWidget(label)
    layout.addWidget(control)
    return wrapper


def hline() -> QWidget:
    """A hairline separator that matches the glass borders."""
    line = QWidget()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {GLASS_BORDER_SOFT};")
    return line


def divider() -> QRectF:  # pragma: no cover - helper for painters
    return QRectF()
