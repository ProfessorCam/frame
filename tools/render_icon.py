#!/usr/bin/env python3
"""Render the frame app icon at multiple sizes using pycairo.

Concept: a charcoal rounded tile (matching the floating pill) with a
selection-reticle (four corner brackets = "capture a region") around a red
record dot.  Reads as "record a screen region" and stays legible at 16px.

Usage:
    python3 tools/render_icon.py [outdir]        # default: icons/
"""
import math
import os
import sys

import cairo


def _rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


def _corner(cr, cx, cy, dx, dy, arm, lw):
    """Draw an L-shaped bracket whose elbow is at (cx, cy)."""
    cr.set_line_width(lw)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(cx, cy + dy * arm)
    cr.line_to(cx, cy)
    cr.line_to(cx + dx * arm, cy)
    cr.stroke()


def draw(size):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surf)
    s = float(size)

    # ── Tile ──────────────────────────────────────────────────────
    pad = s * 0.045
    tile = s - 2 * pad
    radius = s * 0.225
    _rounded_rect(cr, pad, pad, tile, tile, radius)
    g = cairo.LinearGradient(0, pad, 0, pad + tile)
    g.add_color_stop_rgb(0, 0.17, 0.17, 0.20)   # #2c2c33
    g.add_color_stop_rgb(1, 0.09, 0.09, 0.11)   # #17171b
    cr.set_source(g)
    cr.fill_preserve()
    # hairline border
    cr.set_line_width(max(1.0, s * 0.006))
    cr.set_source_rgba(1, 1, 1, 0.09)
    cr.stroke()

    # top inner highlight
    if size >= 48:
        _rounded_rect(cr, pad + s * 0.02, pad + s * 0.02,
                      tile - s * 0.04, tile - s * 0.04, radius * 0.9)
        cr.set_line_width(max(1.0, s * 0.006))
        cr.set_source_rgba(1, 1, 1, 0.05)
        cr.stroke()

    # ── Selection reticle (skip on tiny sizes) ────────────────────
    if size >= 32:
        m = s * 0.24
        arm = s * 0.12
        lw = max(1.2, s * 0.05)
        cr.set_source_rgba(0.96, 0.96, 0.98, 0.85)
        _corner(cr, m,     m,     +1, +1, arm, lw)   # top-left
        _corner(cr, s - m, m,     -1, +1, arm, lw)   # top-right
        _corner(cr, m,     s - m, +1, -1, arm, lw)   # bottom-left
        _corner(cr, s - m, s - m, -1, -1, arm, lw)   # bottom-right

    # ── Record dot with glow ──────────────────────────────────────
    cx = cy = s / 2
    dot = s * (0.20 if size >= 32 else 0.26)

    if size >= 48:
        glow = cairo.RadialGradient(cx, cy, dot * 0.6, cx, cy, dot * 1.9)
        glow.add_color_stop_rgba(0, 1.0, 0.35, 0.30, 0.45)
        glow.add_color_stop_rgba(1, 1.0, 0.35, 0.30, 0.0)
        cr.set_source(glow)
        cr.arc(cx, cy, dot * 1.9, 0, 2 * math.pi)
        cr.fill()

    rg = cairo.RadialGradient(cx - dot * 0.3, cy - dot * 0.3, dot * 0.1,
                              cx, cy, dot)
    rg.add_color_stop_rgb(0, 1.0, 0.46, 0.40)   # #ff756a
    rg.add_color_stop_rgb(1, 0.86, 0.26, 0.22)  # #dc4238
    cr.set_source(rg)
    cr.arc(cx, cy, dot, 0, 2 * math.pi)
    cr.fill()

    return surf


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'icons')
    os.makedirs(outdir, exist_ok=True)
    for size in (16, 32, 48, 64, 128, 256, 512):
        surf = draw(size)
        path = os.path.join(outdir, f'frame-{size}.png')
        surf.write_to_png(path)
        print('wrote', path)


if __name__ == '__main__':
    main()
