"""CoralOS welcome screen application (GTK 4)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from string import Template
from typing import List

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import __version__  # noqa: E402
from .config import WelcomeConfig, load_config, resolve_asset  # noqa: E402
from .readiness import SessionReadiness, SimulatedProbe, build_probes  # noqa: E402
from .ring import AvatarRing  # noqa: E402
from .timeline import Phase, WelcomeTimeline  # noqa: E402
from .user import UserInfo, current_user, format_greeting  # noqa: E402

APP_ID = "os.coral.Welcome"


def log(message: str) -> None:
    print(f"coralos-welcome: {message}", file=sys.stderr, flush=True)


def load_css(config: WelcomeConfig) -> None:
    template = Template((Path(__file__).parent / "style.css").read_text(encoding="utf-8"))
    css = template.safe_substitute(
        accent=config.accent_color, background=config.background_color, text=config.text_color
    )
    provider = Gtk.CssProvider()
    provider.load_from_data(css, -1)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
    )


class WelcomeView:
    """One window (one per monitor) showing the shared timeline state."""

    def __init__(self, app: Gtk.Application, config: WelcomeConfig, user: UserInfo, greeting: str):
        self.window = Gtk.ApplicationWindow(application=app, title="CoralOS")
        self.window.add_css_class("coralos-welcome")
        self.window.set_decorated(False)

        self.stage = Gtk.Overlay()
        self.stage.add_css_class("stage")
        self.window.set_child(self.stage)

        # Layers, bottom to top: wallpaper, shade, glow, avatar column, logo.
        background = resolve_asset(config.background_image)
        if background is not None:
            picture = Gtk.Picture.new_for_filename(str(background))
            picture.set_content_fit(Gtk.ContentFit.COVER)
            picture.set_can_shrink(True)
            self.stage.set_child(picture)
            shade = Gtk.Box()
            shade.add_css_class("shade")
            shade.set_opacity(config.background_dim / 100.0)
            shade.set_can_target(False)
            self.stage.add_overlay(shade)
        glow = Gtk.Box()
        glow.add_css_class("glow")
        glow.set_can_target(False)
        self.stage.add_overlay(glow)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        column.set_halign(Gtk.Align.CENTER)
        column.set_valign(Gtk.Align.CENTER)
        self.ring = AvatarRing(config.avatar_size, config.accent_color, user.initials, user.icon_file)
        column.append(self.ring)
        self.greeting = Gtk.Label(label=greeting)
        self.greeting.add_css_class("greeting")
        column.append(self.greeting)
        self.stage.add_overlay(column)

        if config.show_branding:
            brand = self._branding(config)
            if brand is not None:
                brand.set_halign(Gtk.Align.CENTER)
                brand.set_valign(Gtk.Align.END)
                self.stage.add_overlay(brand)

    @staticmethod
    def _branding(config: WelcomeConfig):
        logo = resolve_asset(config.branding_logo)
        if logo is not None and config.branding_logo_height > 0:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    str(logo), -1, config.branding_logo_height, True
                )
                picture = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
                picture.add_css_class("brand-logo")
                return picture
            except GLib.Error as error:
                log(f"branding logo {logo}: {error.message}")
        if not config.branding_text:
            return None
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        dot = Gtk.Label(label="●")
        dot.add_css_class("brand-dot")
        brand.append(dot)
        text = Gtk.Label(label=config.branding_text.upper())
        text.add_css_class("brand")
        brand.append(text)
        return brand

    def apply(self, frame) -> None:
        self.ring.set_frame(frame)
        self.greeting.set_opacity(frame.intro)
        # Fade the stage, not the window: the window stays transparent so the
        # compositor blends the desktop underneath during the fade.
        self.stage.set_opacity(frame.opacity)


class WelcomeApp(Gtk.Application):
    def __init__(self, args: argparse.Namespace, config: WelcomeConfig):
        flags = Gio.ApplicationFlags.NON_UNIQUE if args.preview else Gio.ApplicationFlags.DEFAULT_FLAGS
        super().__init__(application_id=APP_ID, flags=flags)
        self.args = args
        self.config = config
        self.views: List[WelcomeView] = []
        self.timeline = None
        self.readiness = None
        self.connect("activate", self._on_activate)

    def _make_readiness(self) -> SessionReadiness:
        if self.args.preview:
            return SessionReadiness([SimulatedProbe(self.args.simulate_ms)], settle_ms=0)
        return SessionReadiness(build_probes(self.config), settle_ms=self.config.settle_ms)

    def _on_activate(self, _app):
        if self.views:
            return
        display = Gdk.Display.get_default()
        load_css(self.config)
        user = current_user(self.config)
        greeting = format_greeting(self.config.greeting, user, self.config.name_source)
        log(f"user={user.username} avatar={user.icon_file or 'initials'}")

        monitors = [display.get_monitors().get_item(i) for i in range(display.get_monitors().get_n_items())]
        if not self.config.all_monitors:
            monitors = monitors[:1]
        windowed = self.args.windowed or (self.args.preview and not self.args.fullscreen)
        targets = [None] if windowed or not monitors else monitors

        for monitor in targets:
            view = WelcomeView(self, self.config, user, greeting)
            if monitor is None:
                view.window.set_default_size(1280, 800)
            else:
                # Size to the monitor first so the wallpaper's own size never drives the window.
                geometry = monitor.get_geometry()
                view.window.set_default_size(geometry.width, geometry.height)
                view.window.fullscreen_on_monitor(monitor)
            if self.config.allow_skip:
                self._add_skip_controllers(view.window)
            self.views.append(view)

        self.readiness = self._make_readiness()
        self.readiness.start()
        self.timeline = None
        self.views[0].ring.add_tick_callback(self._tick)
        for view in self.views:
            view.window.present()

        # Last-resort guard in case frames never get scheduled (e.g. hidden window).
        cfg = self.config
        budget = cfg.max_wait_ms + cfg.complete_ms + cfg.check_ms + cfg.success_hold_ms + cfg.fade_ms + 5000
        GLib.timeout_add(budget, self._finish)

    def _add_skip_controllers(self, window):
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        window.add_controller(keys)
        click = Gtk.GestureClick()
        click.connect("released", lambda *a: self._skip())
        window.add_controller(click)

    def _on_key(self, _ctrl, keyval, _code, _state):
        if keyval in (Gdk.KEY_Escape, Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self._skip()
            return True
        return False

    def _skip(self):
        if self.timeline is not None:
            self.timeline.skip()

    def _tick(self, _widget, clock):
        now_ms = clock.get_frame_time() / 1000.0
        if self.timeline is None:
            self.timeline = WelcomeTimeline(self.config, now_ms)
        frame = self.timeline.frame(now_ms, self.readiness.fraction, self.readiness.ready)
        for view in self.views:
            view.apply(frame)
        if self.args.verbose and frame.phase is not getattr(self, "_last_phase", None):
            log(f"phase={frame.phase.value} readiness={self.readiness.fraction:.2f}")
            self._last_phase = frame.phase
        if frame.phase is Phase.DONE:
            if self.args.preview and self.args.loop:
                self.timeline = None
                self.readiness.stop()
                self.readiness = self._make_readiness()
                self.readiness.start()
                return GLib.SOURCE_CONTINUE
            GLib.idle_add(self._finish)
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _finish(self):
        if self.readiness is not None:
            self.readiness.stop()
        for view in self.views:
            view.window.destroy()
        self.views = []
        self.quit()
        return GLib.SOURCE_REMOVE


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="coralos-welcome", description="CoralOS welcome screen")
    parser.add_argument("--preview", action="store_true", help="test run in a window with simulated loading")
    parser.add_argument("--fullscreen", action="store_true", help="with --preview: go fullscreen")
    parser.add_argument("--windowed", action="store_true", help="never go fullscreen")
    parser.add_argument("--loop", action="store_true", help="with --preview: repeat the animation")
    parser.add_argument("--simulate-ms", type=int, default=3000, help="with --preview: fake load time")
    parser.add_argument("--config", help="extra config file layered on top of the others")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    warnings: list = []
    config = load_config(args.config, warnings=warnings)
    for warning in warnings:
        log(f"config: {warning}")
    if not config.enabled and not args.preview:
        log("disabled in welcome.conf; exiting")
        return 0
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        log("no graphical display; exiting")
        return 0
    if not Gtk.init_check():
        log("could not open display; exiting")
        return 0
    return WelcomeApp(args, config).run([sys.argv[0]])
