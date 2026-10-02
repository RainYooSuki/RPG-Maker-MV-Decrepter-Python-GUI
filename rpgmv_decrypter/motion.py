"""Motion: the durations, easings and the small driver everything else uses.

Two rules shape this module.

**No ``QGraphicsEffect``.**  Qt animates opacity most easily with a
``QGraphicsOpacityEffect``, but that renders the widget into a cached offscreen pixmap -
the exact mechanism behind the ghosting ("伪影") reported earlier, and a guard test
forbids any widget from carrying a graphics effect.  So motion animates *painted*
properties instead: a float that a ``paintEvent`` reads.  That also makes the motion
measurable, which is how it is verified.

**Idle must cost nothing.**  A timer that repaints a window forever is worse than no
animation.  :class:`Animation` stops itself when it finishes and a widget repaints only
while something is actually moving.

The durations come from one place so the interface moves at a consistent speed, and the
whole layer can be switched off - ``RPGMV_NO_MOTION=1``, or a platform that asks for
reduced motion.
"""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QObject, QTimer, QVariantAnimation

# ----------------------------------------------------------------------
# durations - one scale, so nothing feels faster or slower than its neighbours
# ----------------------------------------------------------------------
#: A state change the user just caused and expects to see immediately.
DURATION_INSTANT = 90
#: Hover and focus feedback.
DURATION_QUICK = 140
#: A panel appearing, a highlight settling.
DURATION_NORMAL = 220
#: Something the eye should follow rather than just notice.
DURATION_SLOW = 320
#: The entrance, once, on first show.
DURATION_ENTRANCE = 420

#: Stagger between the step cards as they come in.  Small enough to read as one
#: gesture, large enough to see the order.
ENTRANCE_STAGGER_MS = 55

#: How far a card rises as it appears, in pixels.
ENTRANCE_LIFT = 14


def motion_enabled() -> bool:
    """Whether animation should run at all.

    Four inputs, in order:

    * ``RPGMV_NO_MOTION`` - an explicit override, used by this project's own checks and
      available to anyone scripting the tool;
    * Qt's ``offscreen`` platform, where motion is off by default;
    * the platform's "reduce motion" preference (see :func:`system_prefers_reduced_motion`);
    * otherwise on.

    The offscreen rule matters for more than tidiness: an animation makes a test depend
    on wall-clock time, and a suite that has to sleep to settle a fade is slower and
    flakier for no gain - nothing is being looked at.  The animation *logic* is still
    tested, by driving it explicitly (see ``tests/test_motion.py``), and
    ``RPGMV_NO_MOTION=0`` turns motion on under any platform for a check that wants to
    watch it move.
    """
    override = os.environ.get("RPGMV_NO_MOTION", "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return False
    if override in {"0", "false", "no", "off"}:
        return True
    try:
        from PySide6.QtGui import QGuiApplication

        application = QGuiApplication.instance()
        if application is not None and application.platformName() == "offscreen":
            return False
    except (AttributeError, ImportError):  # pragma: no cover - older Qt
        pass
    return not system_prefers_reduced_motion()


#: Cached answer to :func:`system_prefers_reduced_motion`; reading the registry on every
#: animation start would be silly, and the setting does not change mid-run.
_reduced_motion: bool | None = None


def system_prefers_reduced_motion() -> bool:
    """Ask the OS whether the user has asked for less motion.

    On Windows that is *Settings → Accessibility → Visual effects → Animation effects*,
    stored as ``SPI_SETCLIENTAREAANIMATION``.  Qt 6.11 exposes no API for it (there is no
    animation-scale member on ``QStyleHints`` in this build), so the registry is read
    directly.

    Every failure path returns ``False`` - "no preference" - because the honest default
    is to animate, and a missing registry key is not a request for less motion.
    """
    global _reduced_motion
    if _reduced_motion is not None:
        return _reduced_motion
    _reduced_motion = False
    if os.name != "nt":
        return _reduced_motion
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop\WindowMetrics"
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "MinAnimate")
        _reduced_motion = str(value).strip() == "0"
    except (ImportError, OSError, ValueError):  # pragma: no cover - depends on the machine
        _reduced_motion = False
    return _reduced_motion


def reset_cache() -> None:
    """Forget the cached system preference.  For tests that change it."""
    global _reduced_motion
    _reduced_motion = None


def scaled(duration: int) -> int:
    """A duration in milliseconds, or zero when motion is off.

    Call sites pass the token (``DURATION_NORMAL``) rather than a raw number, so a policy
    change lands everywhere at once instead of each site inventing its own.
    """
    return duration if motion_enabled() else 0


class Animation(QObject):
    """Drives one float from A to B, calling ``on_frame`` on every step.

    Thin on purpose: ``QVariantAnimation`` already schedules frames efficiently and stops
    when it reaches the end.  What this adds is

    * a callback-based API, so a widget animates a value it paints rather than having to
      expose a Qt property for every visual knob;
    * the reduce-motion policy, applied once;
    * :meth:`jump_to_end`, so tests and the first paint can settle instantly instead of
      waiting for wall-clock time.

    ``on_frame`` receives values in ``[0, 1]``, not the raw start/end numbers, because
    almost every use is a progress fraction.
    """

    def __init__(
        self,
        on_frame: Callable[[float], None],
        *,
        duration: int = DURATION_NORMAL,
        easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
        on_finished: Callable[[], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_frame = on_frame
        self._on_finished = on_finished
        self._value = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(scaled(duration))
        self._animation.setEasingCurve(easing)
        self._animation.valueChanged.connect(self._on_value)

    # -- state ---------------------------------------------------------
    @property
    def value(self) -> float:
        """The current progress, 0..1.  What a paint event reads."""
        return self._value

    def is_running(self) -> bool:
        return self._animation.state() == QAbstractAnimation.State.Running

    # -- control -------------------------------------------------------
    def start(self) -> None:
        if self._animation.duration() == 0 or not motion_enabled():
            # No motion: land on the end state immediately, so the interface is still
            # correct - just not animated.
            self.jump_to_end()
            return
        self._animation.stop()
        self._animation.start()

    def stop(self) -> None:
        self._animation.stop()

    def jump_to_end(self) -> None:
        """Settle on the finished state without waiting."""
        self._animation.stop()
        self._on_value(1.0)
        if self._on_finished is not None:
            self._on_finished()

    def _on_value(self, value: object) -> None:
        try:
            self._value = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            self._value = 0.0
        self._on_frame(self._value)


class Pulse:
    """A repeating 0..1..0 wave, for "something is happening" states.

    Used for the drop target while a drag hovers over it and for the busy indicator.
    Deliberately not a ``QPropertyAnimation`` on a loop: this needs to be *stopped*
    reliably, and an animation in an infinite loop is easy to leave running by accident.
    """

    def __init__(self, on_frame: Callable[[float], None], *, period_ms: int = 1200) -> None:
        self._on_frame = on_frame
        self._timer = QTimer()
        self._timer.setInterval(max(16, period_ms // 24))
        self._timer.timeout.connect(self._tick)
        self._period = max(1, period_ms)
        self._elapsed = 0
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running or not motion_enabled():
            return
        self._running = True
        self._elapsed = 0
        self._timer.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        self._on_frame(0.0)

    def _tick(self) -> None:
        self._elapsed = (self._elapsed + self._timer.interval()) % self._period
        phase = self._elapsed / self._period
        # A raised cosine: smooth at both ends, no visible seam when it repeats.
        self._on_frame((1.0 - _cos(phase * 6.283185307179586)) / 2.0)


def _cos(radians: float) -> float:
    import math

    return math.cos(radians)


class Stagger:
    """Runs one :class:`Animation` per item, each starting a little after the last.

    Used for the entrance: the three step cards rise in sequence rather than as one
    block, which is what makes the arrival read as designed instead of as a flicker.

    The delays are driven by a single timer rather than by N timers, so the number of
    items cannot turn into a scheduling cost, and :meth:`finish` settles everything at
    once for tests and for the reduce-motion path.
    """

    def __init__(
        self,
        on_frame: Callable[[int, float], None],
        count: int,
        *,
        duration: int = DURATION_ENTRANCE,
        delay_ms: int = ENTRANCE_STAGGER_MS,
        easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
    ) -> None:
        self._on_frame = on_frame
        self._count = max(0, count)
        self._duration = duration
        self._delay = delay_ms
        self._easing = easing
        self._values = [0.0] * self._count
        self._started = [False] * self._count
        self._elapsed = 0
        self._timer = QTimer()
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    @property
    def values(self) -> list[float]:
        return list(self._values)

    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        if self._count == 0:
            return
        if not motion_enabled():
            self.finish()
            return
        self._elapsed = 0
        self._started = [False] * self._count
        self._values = [0.0] * self._count
        self._timer.start()

    def finish(self) -> None:
        """Settle every item on its end state immediately."""
        self._timer.stop()
        for index in range(self._count):
            self._values[index] = 1.0
            self._on_frame(index, 1.0)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._elapsed += self._timer.interval()
        moving = False
        for index in range(self._count):
            delay = index * self._delay
            progress = (self._elapsed - delay) / max(1, self._duration)
            if progress <= 0.0:
                moving = True
                continue
            if progress >= 1.0:
                if not self._started[index]:
                    # Land *exactly* on 1.0.  The timer ticks in 16 ms steps, so the last
                    # step lands at 0.998 and then stops - leaving every surface a
                    # fraction short of settled, which nothing would ever correct.
                    self._started[index] = True
                    self._values[index] = 1.0
                    self._on_frame(index, 1.0)
                continue
            moving = True
            eased = ease_out_cubic(progress)
            self._values[index] = eased
            self._on_frame(index, eased)
        if not moving:
            self._timer.stop()


def ease_out_cubic(value: float) -> float:
    """The same curve :class:`Animation` uses, for callers that position by hand."""
    clamped = min(max(value, 0.0), 1.0)
    return 1.0 - (1.0 - clamped) ** 3
