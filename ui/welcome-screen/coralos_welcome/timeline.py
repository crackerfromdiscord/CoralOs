"""Pure, toolkit-independent animation timeline for the welcome screen.

The GTK layer calls :meth:`WelcomeTimeline.frame` once per frame with the
current time and session readiness and draws whatever :class:`Frame` says.
Keeping this free of GTK makes the choreography easy to unit test.

Phases: LOADING -> COMPLETING (ring sweeps to 100%) -> SUCCESS (checkmark
draws, then holds) -> FADING (whole screen fades out) -> DONE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .config import WelcomeConfig


class Phase(Enum):
    LOADING = "loading"
    COMPLETING = "completing"
    SUCCESS = "success"
    FADING = "fading"
    DONE = "done"


@dataclass
class Frame:
    phase: Phase
    progress: float  # 0..1 sweep of the ring arc
    rotation: float  # radians, slow spin while loading
    ring_spin: float  # 0..1, how much the "busy" arc is still spinning
    check: float  # 0..1 checkmark stroke progress
    opacity: float  # 0..1 opacity of the whole screen
    intro: float  # 0..1 entrance animation


def ease_out_cubic(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


MIN_ARC = 0.08
INTRO_MS = 450
SPIN_PERIOD_MS = 1600


class WelcomeTimeline:
    def __init__(self, config: WelcomeConfig, start_ms: float):
        self.config = config
        self.start_ms = start_ms
        self.phase = Phase.LOADING
        self.phase_start = start_ms
        self.shown_progress = 0.0
        self.progress_at_complete = 0.0
        self.rotation_at_complete = 0.0
        self.last_ms = start_ms
        self.skip_requested = False

    def _enter(self, phase: Phase, now_ms: float) -> None:
        self.phase = phase
        self.phase_start = now_ms

    def skip(self) -> None:
        self.skip_requested = True

    def _rotation(self, now_ms: float) -> float:
        return 2 * math.pi * ((now_ms - self.start_ms) / SPIN_PERIOD_MS)

    def frame(self, now_ms: float, readiness: float, ready: bool) -> Frame:
        cfg = self.config
        dt = max(0.0, now_ms - self.last_ms)
        self.last_ms = now_ms
        elapsed = now_ms - self.start_ms
        in_phase = now_ms - self.phase_start
        intro = ease_out_cubic(elapsed / INTRO_MS)

        if self.phase is Phase.LOADING:
            # Never show 100% while loading; the final sweep is the COMPLETING phase.
            target = MIN_ARC + (0.85 - MIN_ARC) * min(max(readiness, 0.0), 1.0)
            # Exponential approach so jumps in readiness animate smoothly.
            self.shown_progress += (target - self.shown_progress) * (1 - math.exp(-dt / 220.0))
            timed_out = elapsed >= cfg.max_wait_ms
            if self.skip_requested or ((ready or timed_out) and elapsed >= cfg.min_display_ms):
                self.progress_at_complete = self.shown_progress
                self.rotation_at_complete = self._rotation(now_ms)
                self._enter(Phase.COMPLETING, now_ms)
                return self.frame(now_ms, readiness, ready)
            return Frame(self.phase, self.shown_progress, self._rotation(now_ms), 1.0, 0.0, 1.0, intro)

        if self.phase is Phase.COMPLETING:
            t = ease_in_out_cubic(in_phase / max(cfg.complete_ms, 1))
            progress = self.progress_at_complete + (1 - self.progress_at_complete) * t
            # Unwind the spin so the full ring lands at 12 o'clock.
            rotation = self.rotation_at_complete % (2 * math.pi)
            rotation = rotation + ((2 * math.pi) - rotation) * t
            if in_phase >= cfg.complete_ms:
                self._enter(Phase.SUCCESS, now_ms)
                return self.frame(now_ms, readiness, ready)
            return Frame(self.phase, progress, rotation, 1 - t, 0.0, 1.0, intro)

        if self.phase is Phase.SUCCESS:
            check = ease_out_cubic(in_phase / max(cfg.check_ms, 1))
            hold = 0 if self.skip_requested else cfg.success_hold_ms
            if in_phase >= cfg.check_ms + hold:
                self._enter(Phase.FADING, now_ms)
                return self.frame(now_ms, readiness, ready)
            return Frame(self.phase, 1.0, 0.0, 0.0, check, 1.0, intro)

        if self.phase is Phase.FADING:
            t = ease_in_out_cubic(in_phase / max(cfg.fade_ms, 1))
            if in_phase >= cfg.fade_ms:
                self._enter(Phase.DONE, now_ms)
                return Frame(Phase.DONE, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0)
            return Frame(self.phase, 1.0, 0.0, 0.0, 1.0, 1 - t, 1.0)

        return Frame(Phase.DONE, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0)
