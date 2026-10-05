"""The avatar + progress ring + checkmark widget, drawn with Cairo."""

from __future__ import annotations

import math
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gtk, Pango, PangoCairo  # noqa: E402

from .timeline import Frame, Phase  # noqa: E402

RING_GAP = 12
RING_WIDTH = 4.0
GLOW_WIDTH = 14.0
CHECK_POINTS = ((-0.34, 0.02), (-0.10, 0.27), (0.36, -0.24))


def parse_rgba(value: str) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    if not rgba.parse(value):
        rgba.parse("#FF7A66")
    return rgba


class AvatarRing(Gtk.DrawingArea):
    def __init__(self, size: int, accent: str, initials: str, icon_file: Optional[str]):
        super().__init__()
        self.size = size
        self.accent = parse_rgba(accent)
        self.initials = initials
        self.frame: Optional[Frame] = None
        self._source: Optional[GdkPixbuf.Pixbuf] = None
        self._scaled: Optional[GdkPixbuf.Pixbuf] = None
        self._scaled_key = None
        if icon_file:
            try:
                self._source = GdkPixbuf.Pixbuf.new_from_file(icon_file)
            except Exception:
                self._source = None
        extent = size + 2 * (RING_GAP + GLOW_WIDTH)
        self.set_content_width(extent)
        self.set_content_height(extent)
        self.set_halign(Gtk.Align.CENTER)
        self.set_draw_func(self._draw)

    def set_frame(self, frame: Frame) -> None:
        self.frame = frame
        self.queue_draw()

    # -- drawing -----------------------------------------------------------
    def _draw(self, _area, cr, width, height):
        frame = self.frame
        if frame is None:
            return
        cx, cy = width / 2, height / 2
        radius = self.size / 2
        ring_radius = radius + RING_GAP

        intro = frame.intro
        cr.translate(cx, cy)
        scale = 0.94 + 0.06 * intro
        cr.scale(scale, scale)
        cr.push_group()

        self._draw_avatar(cr, radius, frame.check)
        self._draw_ring(cr, ring_radius, frame)
        if frame.check > 0:
            self._draw_check(cr, radius, frame.check)

        cr.pop_group_to_source()
        cr.paint_with_alpha(intro)

    def _draw_avatar(self, cr, radius, check=0.0):
        cr.save()
        cr.new_path()
        cr.arc(0, 0, radius, 0, 2 * math.pi)
        cr.clip()
        pixbuf = self._avatar_pixbuf(radius)
        if pixbuf is not None:
            factor = self.get_scale_factor()
            cr.translate(-radius, -radius)
            cr.scale(1 / factor, 1 / factor)
            offset_x = (pixbuf.get_width() - 2 * radius * factor) / 2
            offset_y = (pixbuf.get_height() - 2 * radius * factor) / 2
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, -offset_x, -offset_y)
            cr.paint()
        else:
            self._draw_initials(cr, radius, 1.0 - check)
        cr.restore()

        # Text rendering leaves a current point behind; start a fresh path.
        cr.new_path()
        cr.arc(0, 0, radius, 0, 2 * math.pi)
        cr.set_source_rgba(1, 1, 1, 0.08)
        cr.set_line_width(1)
        cr.stroke()

    def _avatar_pixbuf(self, radius):
        if self._source is None:
            return None
        factor = self.get_scale_factor()
        diameter = max(1, int(round(2 * radius * factor)))
        if self._scaled_key != diameter:
            src = self._source
            cover = max(diameter / src.get_width(), diameter / src.get_height())
            self._scaled = src.scale_simple(
                max(diameter, int(math.ceil(src.get_width() * cover))),
                max(diameter, int(math.ceil(src.get_height() * cover))),
                GdkPixbuf.InterpType.HYPER,
            )
            self._scaled_key = diameter
        return self._scaled

    def _draw_initials(self, cr, radius, text_alpha=1.0):
        a = self.accent
        import cairo

        gradient = cairo.LinearGradient(-radius, -radius, radius, radius)
        gradient.add_color_stop_rgb(0, a.red * 0.9 + 0.1, a.green * 0.8 + 0.1, a.blue * 0.8 + 0.15)
        gradient.add_color_stop_rgb(1, a.red * 0.35, a.green * 0.25, a.blue * 0.35 + 0.1)
        cr.set_source(gradient)
        cr.paint()

        layout = PangoCairo.create_layout(cr)
        font = Pango.FontDescription.from_string("Sans")
        font.set_weight(Pango.Weight.SEMILIGHT)
        font.set_absolute_size(radius * 0.72 * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_text(self.initials, -1)
        _ink, logical = layout.get_pixel_extents()
        cr.move_to(-logical.width / 2 - logical.x, -logical.height / 2 - logical.y)
        cr.set_source_rgba(1, 1, 1, 0.95 * text_alpha)
        PangoCairo.show_layout(cr, layout)

    def _draw_ring(self, cr, ring_radius, frame: Frame):
        a = self.accent
        import cairo

        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.new_path()
        cr.arc(0, 0, ring_radius, 0, 2 * math.pi)
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.set_line_width(RING_WIDTH)
        cr.stroke()

        progress = min(max(frame.progress, 0.0), 1.0)
        if progress <= 0:
            return
        start = -math.pi / 2 + frame.rotation
        end = start + 2 * math.pi * progress

        glow = 0.10 + 0.08 * (1 - frame.ring_spin)
        cr.set_source_rgba(a.red, a.green, a.blue, glow)
        cr.set_line_width(GLOW_WIDTH)
        cr.arc(0, 0, ring_radius, start, end)
        cr.stroke()

        cr.set_source_rgba(a.red, a.green, a.blue, 1.0)
        cr.set_line_width(RING_WIDTH)
        if progress >= 0.999:
            cr.arc(0, 0, ring_radius, 0, 2 * math.pi)
        else:
            cr.arc(0, 0, ring_radius, start, end)
        cr.stroke()

    def _draw_check(self, cr, radius, amount):
        import cairo

        cr.new_path()
        cr.arc(0, 0, radius, 0, 2 * math.pi)
        cr.set_source_rgba(0.02, 0.03, 0.05, 0.62 * min(1.0, amount * 1.6))
        cr.fill()

        points = [(x * radius, y * radius) for x, y in CHECK_POINTS]
        lengths = [math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)]
        remaining = sum(lengths) * amount
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_line_width(max(4.0, radius * 0.075))
        cr.set_source_rgba(1, 1, 1, 1)
        cr.move_to(*points[0])
        for (x0, y0), (x1, y1), length in zip(points, points[1:], lengths):
            if remaining <= 0:
                break
            t = min(1.0, remaining / length)
            cr.line_to(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
            remaining -= length
        cr.stroke()


__all__ = ["AvatarRing", "Phase", "parse_rgba"]
