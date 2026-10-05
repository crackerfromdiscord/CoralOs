import math

from coralos_welcome.config import WelcomeConfig
from coralos_welcome.timeline import Phase, WelcomeTimeline

CFG = WelcomeConfig(min_display_ms=1000, max_wait_ms=5000, complete_ms=400, check_ms=400,
                    success_hold_ms=600, fade_ms=500)


def run(timeline, until_ms, readiness, ready, step=16):
    t, frames = 0.0, []
    while t <= until_ms:
        frames.append((t, timeline.frame(t, readiness(t), ready(t))))
        t += step
    return frames


def test_full_sequence_when_ready_early():
    tl = WelcomeTimeline(CFG, 0)
    frames = run(tl, 4000, lambda t: 1.0, lambda t: True)
    phases = [f.phase for _, f in frames]
    # waits for min_display_ms even though the session was ready immediately
    assert all(p is Phase.LOADING for t, f in frames if t < 1000 for p in [f.phase])
    order = [p for i, p in enumerate(phases) if i == 0 or phases[i - 1] is not p]
    assert order == [Phase.LOADING, Phase.COMPLETING, Phase.SUCCESS, Phase.FADING, Phase.DONE]
    done_at = next(t for t, f in frames if f.phase is Phase.DONE)
    assert 1000 + 400 + 400 + 600 + 500 <= done_at <= 1000 + 400 + 400 + 600 + 500 + 64


def test_progress_never_completes_while_loading_and_is_monotonic():
    tl = WelcomeTimeline(CFG, 0)
    frames = run(tl, 3000, lambda t: min(1.0, t / 3000), lambda t: False)
    progress = [f.progress for _, f in frames]
    assert all(f.phase is Phase.LOADING for _, f in frames)
    assert max(progress) < 0.9
    assert all(b >= a - 1e-9 for a, b in zip(progress, progress[1:]))


def test_timeout_never_blocks_login():
    tl = WelcomeTimeline(CFG, 0)
    frames = run(tl, 9000, lambda t: 0.0, lambda t: False)
    assert frames[-1][1].phase is Phase.DONE
    left_loading = next(t for t, f in frames if f.phase is not Phase.LOADING)
    assert CFG.max_wait_ms <= left_loading < CFG.max_wait_ms + 32


def test_checkmark_and_fade_values():
    tl = WelcomeTimeline(CFG, 0)
    frames = run(tl, 4000, lambda t: 1.0, lambda t: True)
    success = [f for _, f in frames if f.phase is Phase.SUCCESS]
    assert success[0].check < 0.5 and success[-1].check == 1.0
    assert all(f.progress == 1.0 and f.opacity == 1.0 for f in success)
    fading = [f.opacity for _, f in frames if f.phase is Phase.FADING]
    assert fading[0] > 0.9 and fading[-1] < 0.1
    completing = [f for _, f in frames if f.phase is Phase.COMPLETING]
    assert math.isclose(completing[-1].rotation % (2 * math.pi), 0, abs_tol=0.3) or \
        math.isclose(completing[-1].rotation, 2 * math.pi, abs_tol=0.3)


def test_skip_shortcuts_the_wait():
    tl = WelcomeTimeline(CFG, 0)
    tl.frame(0, 0.0, False)
    tl.skip()
    assert tl.frame(100, 0.0, False).phase is Phase.COMPLETING
