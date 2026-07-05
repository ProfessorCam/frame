"""frame GTK4 application – screen area recorder for GNOME Wayland.

The UI is a wide, flat, translucent "pill" – a floating macOS-style controller
that morphs between an idle state (format / delay / monitor / record) and a
recording state (timer / size / pause / stop).
"""

import os
import subprocess
import tempfile
from datetime import datetime

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

import cairo
from gi.repository import Adw, Gdk, GLib, Gtk

from frame import __version__, recorder
from frame.config import Config
from frame.overlay import CountdownOverlay
from frame.dbus_control import DBusControl
from frame import globalshortcuts

# ── CSS ───────────────────────────────────────────────────────────────

CSS = """\
window.frame-root {
    background: transparent;
}

.frame-pill {
    background: linear-gradient(180deg,
        rgba(44, 44, 50, 0.94), rgba(28, 28, 33, 0.94));
    border-radius: 26px;
    border: 1px solid rgba(255, 255, 255, 0.09);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5),
                inset 0 1px 0 rgba(255, 255, 255, 0.06);
    padding: 7px 10px;
    color: #f5f5f7;
}

.frame-toast {
    background: rgba(28, 28, 33, 0.94);
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.45);
    padding: 6px 12px;
    color: #f5f5f7;
    margin-top: 8px;
}

.brand-dot {
    min-width: 13px;
    min-height: 13px;
    border-radius: 7px;
    background: linear-gradient(135deg, #ff6a5e, #e0483d);
    margin: 0 8px 0 6px;
    box-shadow: 0 0 8px rgba(224, 72, 61, 0.55);
}

.rec-dot {
    min-width: 13px;
    min-height: 13px;
    border-radius: 7px;
    background: #ff453a;
    margin: 0 6px 0 8px;
    box-shadow: 0 0 10px rgba(255, 69, 58, 0.8);
}

/* Segmented format switch */
.segmented {
    background: rgba(255, 255, 255, 0.07);
    border-radius: 13px;
    padding: 2px;
}
.segmented button {
    background: transparent;
    border: none;
    box-shadow: none;
    outline: none;
    min-height: 22px;
    padding: 3px 13px;
    border-radius: 11px;
    color: rgba(245, 245, 247, 0.62);
    font-weight: 600;
    font-size: 12px;
}
.segmented button:hover { color: #f5f5f7; }
.segmented button:checked {
    background: rgba(255, 255, 255, 0.18);
    color: #ffffff;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
}

/* Flat icon-ish pill buttons (delay, monitor, settings, close) */
.pill-flat, .pill-flat > button {
    background: rgba(255, 255, 255, 0.05);
    border: none;
    box-shadow: none;
    border-radius: 12px;
    color: rgba(245, 245, 247, 0.85);
    padding: 4px 8px;
    min-height: 22px;
}
.pill-flat:hover, .pill-flat > button:hover {
    background: rgba(255, 255, 255, 0.12);
    color: #ffffff;
}

.pill-flat dropdown,
.pill-flat > button {
    font-size: 12px;
}

.close-btn {
    background: transparent;
    color: rgba(245, 245, 247, 0.55);
    border-radius: 11px;
    min-width: 22px;
    min-height: 22px;
    padding: 0;
}
.close-btn:hover {
    background: rgba(255, 255, 255, 0.12);
    color: #ffffff;
}

/* Record / stop / pause */
.record-btn {
    background: linear-gradient(180deg, #ff5a4e, #e0483d);
    color: #ffffff;
    font-weight: 700;
    border: none;
    border-radius: 15px;
    padding: 5px 16px 5px 12px;
    box-shadow: 0 2px 8px rgba(224, 72, 61, 0.45);
}
.record-btn:hover { background: linear-gradient(180deg, #ff6b60, #e85246); }
.record-btn:disabled { opacity: 0.5; }
.record-btn .dot {
    min-width: 9px; min-height: 9px; border-radius: 5px;
    background: #ffffff; margin-right: 8px;
}

.stop-btn {
    background: rgba(255, 255, 255, 0.14);
    color: #ffffff;
    font-weight: 700;
    border: none;
    border-radius: 15px;
    padding: 5px 16px;
}
.stop-btn:hover { background: rgba(255, 255, 255, 0.22); }

.timer {
    font-family: monospace;
    font-size: 15px;
    font-weight: 700;
    color: #ff453a;
    margin: 0 4px;
}
.timer.paused { color: #f5a623; }
.size-label {
    font-size: 12px;
    color: rgba(245, 245, 247, 0.55);
    margin-right: 6px;
}

.toast-text { font-size: 12px; color: rgba(245, 245, 247, 0.9); }
.toast-text.error { color: #ff6b60; }
.toast-text.done  { color: #4cd964; }
.toast-action > button, .toast-action {
    background: rgba(255, 255, 255, 0.09);
    border: none; box-shadow: none;
    border-radius: 10px;
    color: #f5f5f7;
    font-size: 12px;
    padding: 3px 10px;
    min-height: 20px;
}
.toast-action:hover { background: rgba(255, 255, 255, 0.18); }

.settings-pop { padding: 6px; }
.settings-pop label { color: inherit; }
.version-label {
    font-size: 11px;
    color: rgba(245, 245, 247, 0.4);
}
"""

# ── Screenshot helper ─────────────────────────────────────────────────


def _take_screenshot(path, connector):
    """Take a screenshot of a specific monitor."""
    # Try CLI tools first (they grab the whole desktop but it's better than nothing)
    for cmd in [['gnome-screenshot', '-f', path], ['grim', path]]:
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=5)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return True
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired):
            continue
    # Fallback: Mutter ScreenCast single-frame capture of the specific monitor
    return recorder.capture_screenshot(path, connector=connector)


# ── Selection window (screenshot background) ─────────────────────────


class SelectionWindow(Gtk.Window):
    """Fullscreen window showing a screenshot. User drags to select a region."""

    def __init__(self, app, screenshot_path, monitor_offset, on_selected,
                 on_cancelled, gdk_monitor=None):
        """
        Args:
            monitor_offset: (ox, oy) – the monitor's position in compositor
                space.  Added to drag coordinates so RecordArea gets absolute
                compositor coordinates.
            gdk_monitor: the ``Gdk.Monitor`` to pin this overlay to.  Using
                ``fullscreen_on_monitor`` guarantees the overlay lands on the
                *same* monitor whose screenshot it shows – essential for a
                correct multi-monitor selection.
        """
        super().__init__(application=app)
        self._on_selected = on_selected
        self._on_cancelled = on_cancelled
        self._screenshot_path = screenshot_path
        self._ox, self._oy = monitor_offset

        self.set_decorated(False)
        if gdk_monitor is not None:
            self.fullscreen_on_monitor(gdk_monitor)
        else:
            self.fullscreen()
        self.set_cursor(Gdk.Cursor.new_from_name('crosshair'))

        self._sx = self._sy = self._cx = self._cy = 0.0
        self._dragging = False

        overlay = Gtk.Overlay()

        if screenshot_path and os.path.exists(screenshot_path):
            pic = Gtk.Picture.new_for_filename(screenshot_path)
            pic.set_content_fit(Gtk.ContentFit.FILL)
            overlay.set_child(pic)
        else:
            overlay.set_child(Gtk.Box(vexpand=True))

        self._canvas = Gtk.DrawingArea()
        self._canvas.set_draw_func(self._draw)
        self._canvas.set_can_target(True)
        overlay.add_overlay(self._canvas)
        self.set_child(overlay)

        drag = Gtk.GestureDrag.new()
        drag.connect('drag-begin', self._begin)
        drag.connect('drag-update', self._update)
        drag.connect('drag-end', self._end)
        self._canvas.add_controller(drag)

        esc = Gtk.ShortcutController()
        esc.set_scope(Gtk.ShortcutScope.GLOBAL)
        esc.add_shortcut(Gtk.Shortcut.new(
            Gtk.KeyvalTrigger.new(Gdk.KEY_Escape, 0),
            Gtk.CallbackAction.new(lambda *_: self._cancel()),
        ))
        self.add_controller(esc)

    def _rect(self):
        x = min(self._sx, self._cx)
        y = min(self._sy, self._cy)
        return x, y, abs(self._cx - self._sx), abs(self._cy - self._sy)

    def _draw(self, _a, cr, width, height):
        if not self._dragging:
            cr.set_source_rgba(0, 0, 0, 0.25)
            cr.paint()
            cr.set_source_rgba(1, 1, 1, 0.8)
            cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL,
                                cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(22)
            txt = 'Drag to select the recording area  •  Esc to cancel'
            ext = cr.text_extents(txt)
            cr.move_to((width - ext.width) / 2, (height + ext.height) / 2)
            cr.show_text(txt)
            return

        x, y, w, h = self._rect()

        # Dim everything AROUND the selection
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.rectangle(0, 0, width, y); cr.fill()
        cr.rectangle(0, y + h, width, height - y - h); cr.fill()
        cr.rectangle(0, y, x, h); cr.fill()
        cr.rectangle(x + w, y, width - x - w, h); cr.fill()

        # Red border
        cr.set_source_rgba(0.91, 0.30, 0.24, 0.95)
        cr.set_line_width(2)
        cr.rectangle(x, y, w, h)
        cr.stroke()

        # Dimension label
        cr.select_font_face('monospace', cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(14)
        label = f'{int(w)} × {int(h)}'
        ext = cr.text_extents(label)
        lx = x + (w - ext.width) / 2
        ly = y + h + 22
        if ly + 4 > height:
            ly = y - 10
        pad = 5
        cr.set_source_rgba(0, 0, 0, 0.7)
        cr.rectangle(lx - pad, ly - ext.height - pad,
                     ext.width + 2 * pad, ext.height + 2 * pad)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.move_to(lx, ly)
        cr.show_text(label)

    def _begin(self, _g, x, y):
        self._sx, self._sy = x, y
        self._cx, self._cy = x, y
        self._dragging = True

    def _update(self, _g, dx, dy):
        self._cx = self._sx + dx
        self._cy = self._sy + dy
        self._canvas.queue_draw()

    def _end(self, _g, dx, dy):
        self._cx = self._sx + dx
        self._cy = self._sy + dy
        x, y, w, h = self._rect()
        self._dragging = False
        self._cleanup_file()
        self.close()
        if w > 20 and h > 20:
            # Convert window-local coordinates → absolute compositor coordinates
            self._on_selected(int(x + self._ox), int(y + self._oy),
                              int(w), int(h))
        else:
            self._on_cancelled()

    def _cancel(self):
        self._cleanup_file()
        self.close()
        self._on_cancelled()

    def _cleanup_file(self):
        if self._screenshot_path and os.path.exists(self._screenshot_path):
            try:
                os.unlink(self._screenshot_path)
            except OSError:
                pass


# ── Main window (the pill) ────────────────────────────────────────────


DELAYS = [0, 3, 5, 10]
FRAMERATES = [24, 30, 60]
FORMATS = ['gif', 'webm', 'mp4']


class FrameWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Frame')
        self.add_css_class('frame-root')
        self.set_decorated(False)   # frameless – the pill IS the window
        self.set_resizable(False)
        self.set_default_size(-1, -1)

        self._app = app
        self._cfg = Config()
        self._rec = recorder.Recorder()
        self._recording = False
        self._timer_id = None
        self._timer_secs = 0
        self._area = None
        self._last_saved = None
        self._monitors = recorder.get_monitors()
        self._sel_windows = []
        self._sel_done = False

        self._apply_css()
        self._build_ui()
        self._build_shortcuts()
        self._setup_remote_control()
        self.connect('close-request', self._on_close)

    # ── Remote control (D-Bus + global shortcuts) ─────────────────
    def _setup_remote_control(self):
        """Export the control interface and register global shortcuts so the
        top-bar extension and system hotkeys can pause/stop the recording."""
        self._dbus = None
        self._gshortcuts = None
        conn = self._app.get_dbus_connection()
        if conn is None:
            return

        self._dbus = DBusControl(
            conn,
            handlers={
                'pause': lambda: GLib.idle_add(self._remote_pause),
                'resume': lambda: GLib.idle_add(self._remote_resume),
                'toggle': lambda: GLib.idle_add(self._remote_toggle),
                'stop': lambda: GLib.idle_add(self._remote_stop),
            },
            state_provider=lambda: (self._recording, self._rec.is_paused),
        )
        self._dbus.register()

        self._gshortcuts = globalshortcuts.GlobalShortcuts(
            conn, self._on_global_shortcut)
        try:
            self._gshortcuts.start()
        except Exception:
            self._gshortcuts = None

    def _emit_state(self):
        if self._dbus:
            self._dbus.emit_state()

    # Handlers invoked from D-Bus / hotkeys (always on the main thread).
    def _remote_pause(self):
        if self._recording and not self._rec.is_paused:
            self._on_pause()
        return False

    def _remote_resume(self):
        if self._recording and self._rec.is_paused:
            self._on_pause()
        return False

    def _remote_toggle(self):
        if self._recording:
            self._on_pause()
        return False

    def _remote_stop(self):
        if self._recording:
            self._on_stop()
        return False

    def _on_global_shortcut(self, shortcut_id):
        if shortcut_id == globalshortcuts.STOP:
            GLib.idle_add(self._remote_stop)
        elif shortcut_id == globalshortcuts.TOGGLE_PAUSE:
            GLib.idle_add(self._remote_toggle)

    @staticmethod
    def _apply_css():
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                       margin_top=12, margin_bottom=12,
                       margin_start=14, margin_end=14)
        self.set_child(root)

        # Pill (draggable via WindowHandle)
        handle = Gtk.WindowHandle()
        pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pill.add_css_class('frame-pill')
        handle.set_child(pill)
        root.append(handle)
        self._pill = pill

        # ── Idle cluster ──────────────────────────────────────────
        self._idle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                             hexpand=True)
        pill.append(self._idle)

        brand = Gtk.Box(valign=Gtk.Align.CENTER)
        brand.set_size_request(13, 13)
        brand.add_css_class('brand-dot')
        self._idle.append(brand)

        # Segmented format control
        seg = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        seg.add_css_class('segmented')
        self._fmt_btns = {}
        first = None
        for fmt in FORMATS:
            btn = Gtk.ToggleButton(label=fmt.upper())
            if first is None:
                first = btn
            else:
                btn.set_group(first)
            btn.connect('toggled', self._on_fmt_toggled, fmt)
            seg.append(btn)
            self._fmt_btns[fmt] = btn
        self._idle.append(seg)

        # Delay dropdown
        self._delay_drop = Gtk.DropDown.new_from_strings(
            ['No delay', '3 s', '5 s', '10 s'])
        self._delay_drop.add_css_class('pill-flat')
        self._delay_drop.set_tooltip_text('Countdown before recording')
        self._delay_drop.connect('notify::selected', self._on_delay)
        self._idle.append(self._delay_drop)

        # Monitor dropdown (only when >1 monitor)
        if len(self._monitors) > 1:
            labels = [f'{c}  ({w}×{h})'
                      for c, _x, _y, w, h in self._monitors]
            self._mon_drop = Gtk.DropDown.new_from_strings(labels)
            self._mon_drop.add_css_class('pill-flat')
            self._mon_drop.set_tooltip_text('Monitor to capture')
            self._mon_drop.connect('notify::selected', self._on_monitor)
            self._idle.append(self._mon_drop)
        else:
            self._mon_drop = None

        # Settings (gear) popover
        self._idle.append(self._build_settings_button())

        # Spacer pushes Record to the right
        self._idle.append(Gtk.Box(hexpand=True))

        # Record button
        self._rec_btn = Gtk.Button()
        self._rec_btn.add_css_class('record-btn')
        rec_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        dot = Gtk.Box(valign=Gtk.Align.CENTER)
        dot.set_size_request(9, 9)
        dot.add_css_class('dot')
        rec_content.append(dot)
        rec_content.append(Gtk.Label(label='Record'))
        self._rec_btn.set_child(rec_content)
        self._rec_btn.set_tooltip_text('Record  (Ctrl+R)')
        self._rec_btn.connect('clicked', lambda _: self._on_record())
        self._idle.append(self._rec_btn)

        # Close button
        close = Gtk.Button(icon_name='window-close-symbolic')
        close.add_css_class('close-btn')
        close.set_tooltip_text('Quit  (Esc)')
        close.connect('clicked', lambda _: self.close())
        self._idle.append(close)

        # ── Recording cluster (hidden initially) ──────────────────
        self._rec_cluster = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                    spacing=8, hexpand=True)
        self._rec_cluster.set_visible(False)
        pill.append(self._rec_cluster)

        rdot = Gtk.Box(valign=Gtk.Align.CENTER)
        rdot.set_size_request(13, 13)
        rdot.add_css_class('rec-dot')
        self._rec_cluster.append(rdot)

        self._timer_lbl = Gtk.Label(label='0:00')
        self._timer_lbl.add_css_class('timer')
        self._rec_cluster.append(self._timer_lbl)

        self._size_lbl = Gtk.Label(label='')
        self._size_lbl.add_css_class('size-label')
        self._rec_cluster.append(self._size_lbl)

        self._rec_cluster.append(Gtk.Box(hexpand=True))

        self._pause_btn = Gtk.Button(label='Pause')
        self._pause_btn.add_css_class('stop-btn')
        self._pause_btn.set_tooltip_text('Pause / Resume  (Space)')
        self._pause_btn.connect('clicked', lambda _: self._on_pause())
        self._rec_cluster.append(self._pause_btn)

        self._stop_btn = Gtk.Button(label='Stop')
        self._stop_btn.add_css_class('record-btn')
        self._stop_btn.set_tooltip_text('Stop  (Ctrl+R / Esc)')
        self._stop_btn.connect('clicked', lambda _: self._on_stop())
        self._rec_cluster.append(self._stop_btn)

        # ── Toast (status + post-save actions) ────────────────────
        self._toast = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._toast.add_css_class('frame-toast')
        self._toast.set_visible(False)
        self._toast_lbl = Gtk.Label(label='')
        self._toast_lbl.add_css_class('toast-text')
        self._toast_lbl.set_wrap(True)
        self._toast.append(self._toast_lbl)
        self._toast_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                     spacing=6)
        self._toast.append(Gtk.Box(hexpand=True))
        self._toast.append(self._toast_actions)
        root.append(self._toast)

        # Restore saved settings into widgets
        self._restore_settings()

    def _build_settings_button(self):
        btn = Gtk.MenuButton(icon_name='emblem-system-symbolic')
        btn.add_css_class('pill-flat')
        btn.set_tooltip_text('Settings')

        pop = Gtk.Popover()
        pop.add_css_class('settings-pop')
        grid = Gtk.Grid(row_spacing=10, column_spacing=12,
                        margin_top=8, margin_bottom=8,
                        margin_start=8, margin_end=8)

        grid.attach(Gtk.Label(label='Capture cursor', xalign=0), 0, 0, 1, 1)
        self._cursor_sw = Gtk.Switch(halign=Gtk.Align.END)
        self._cursor_sw.connect('notify::active', self._on_cursor)
        grid.attach(self._cursor_sw, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label='Frame rate', xalign=0), 0, 1, 1, 1)
        self._fps_drop = Gtk.DropDown.new_from_strings(
            [f'{f} fps' for f in FRAMERATES])
        self._fps_drop.connect('notify::selected', self._on_fps)
        grid.attach(self._fps_drop, 1, 1, 1, 1)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(4)
        grid.attach(sep, 0, 2, 2, 1)

        ver = Gtk.Label(label=f'Frame {__version__}', xalign=1)
        ver.add_css_class('version-label')
        grid.attach(ver, 0, 3, 2, 1)

        pop.set_child(grid)
        btn.set_popover(pop)
        return btn

    def _restore_settings(self):
        fmt = self._cfg['format']
        if fmt in self._fmt_btns:
            self._fmt_btns[fmt].set_active(True)
        else:
            self._fmt_btns['gif'].set_active(True)

        try:
            self._delay_drop.set_selected(DELAYS.index(self._cfg['delay']))
        except ValueError:
            self._delay_drop.set_selected(0)

        if self._mon_drop is not None:
            idx = self._cfg['monitor']
            if 0 <= idx < len(self._monitors):
                self._mon_drop.set_selected(idx)
            else:
                # Default to monitor at (0,0)
                for i, (_c, mx, my, _w, _h) in enumerate(self._monitors):
                    if mx == 0 and my == 0:
                        self._mon_drop.set_selected(i)
                        break

        self._cursor_sw.set_active(bool(self._cfg['cursor']))
        try:
            self._fps_drop.set_selected(FRAMERATES.index(self._cfg['framerate']))
        except ValueError:
            self._fps_drop.set_selected(FRAMERATES.index(30))

    def _build_shortcuts(self):
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.GLOBAL)
        ctrl.add_shortcut(Gtk.Shortcut.new(
            Gtk.KeyvalTrigger.new(Gdk.KEY_r, Gdk.ModifierType.CONTROL_MASK),
            Gtk.CallbackAction.new(lambda *_: self._on_record_or_stop())))
        ctrl.add_shortcut(Gtk.Shortcut.new(
            Gtk.KeyvalTrigger.new(Gdk.KEY_Escape, 0),
            Gtk.CallbackAction.new(lambda *_: self._on_escape())))
        ctrl.add_shortcut(Gtk.Shortcut.new(
            Gtk.KeyvalTrigger.new(Gdk.KEY_space, 0),
            Gtk.CallbackAction.new(lambda *_: self._on_space())))
        self.add_controller(ctrl)

    # ── Settings handlers ─────────────────────────────────────────

    def _on_fmt_toggled(self, btn, fmt):
        if btn.get_active():
            self._cfg.set('format', fmt)

    def _on_delay(self, drop, _p):
        self._cfg.set('delay', DELAYS[drop.get_selected()])

    def _on_monitor(self, drop, _p):
        self._cfg.set('monitor', drop.get_selected())

    def _on_cursor(self, sw, _p):
        self._cfg.set('cursor', sw.get_active())

    def _on_fps(self, drop, _p):
        self._cfg.set('framerate', FRAMERATES[drop.get_selected()])

    # ── Monitor helpers ───────────────────────────────────────────

    def _selected_monitor(self):
        """Return (connector, x, y, w, h) for the chosen monitor."""
        if not self._monitors:
            return None
        idx = self._mon_drop.get_selected() if self._mon_drop else 0
        if idx >= len(self._monitors):
            idx = 0
        return self._monitors[idx]

    # ── Toast / status ────────────────────────────────────────────

    def _clear_toast_actions(self):
        child = self._toast_actions.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._toast_actions.remove(child)
            child = nxt

    def _toast_msg(self, text, cls=None, actions=None):
        for c in ('error', 'done'):
            self._toast_lbl.remove_css_class(c)
        if cls:
            self._toast_lbl.add_css_class(cls)
        self._toast_lbl.set_text(text)
        self._clear_toast_actions()
        for label, cb in (actions or []):
            b = Gtk.Button(label=label)
            b.add_css_class('toast-action')
            b.connect('clicked', lambda _w, fn=cb: fn())
            self._toast_actions.append(b)
        self._toast.set_visible(True)

    def _hide_toast(self):
        self._toast.set_visible(False)

    # ── Actions ───────────────────────────────────────────────────

    def _on_record_or_stop(self):
        if self._recording:
            self._on_stop()
        else:
            self._on_record()

    def _on_space(self):
        if self._recording:
            self._on_pause()

    def _on_record(self):
        if self._recording:
            return
        self._rec_btn.set_sensitive(False)
        self._hide_toast()
        GLib.timeout_add(80, self._do_screenshot)

    def _on_stop(self):
        if self._recording:
            self._rec.stop()

    def _on_pause(self):
        if not self._recording:
            return
        if self._rec.is_paused:
            if self._rec.resume():
                self._pause_btn.set_label('Pause')
                self._timer_lbl.remove_css_class('paused')
                self._emit_state()
        else:
            if self._rec.pause():
                self._pause_btn.set_label('Resume')
                self._timer_lbl.add_css_class('paused')
                self._emit_state()

    def _on_escape(self):
        if self._recording:
            self._on_stop()
        else:
            self.close()

    # ── Screenshot + selection ────────────────────────────────────

    def _do_screenshot(self):
        if not self._monitors:
            self.present()
            self._rec_btn.set_sensitive(True)
            self._toast_msg('No monitor found', 'error')
            return False

        display = Gdk.Display.get_default()
        single = len(self._monitors) == 1
        self._sel_done = False
        self._sel_windows = []

        # One overlay per monitor, each pinned to its monitor with its own
        # 1:1 screenshot.  The user drags on whichever monitor they like;
        # the first completed selection wins and closes the rest.
        for connector, mx, my, _mw, _mh in self._monitors:
            tmp = os.path.join(tempfile.gettempdir(),
                               f'frame_bg_{connector}.png')
            if single:
                _take_screenshot(tmp, connector)
            else:
                # gnome-screenshot grabs the whole desktop, which distorts a
                # per-monitor overlay – use Mutter's per-monitor capture.
                recorder.capture_screenshot(tmp, connector=connector)
            bg = tmp if os.path.exists(tmp) else None

            sel = SelectionWindow(
                self._app, bg,
                monitor_offset=(mx, my),
                gdk_monitor=self._gdk_monitor_for_connector(display, connector),
                on_selected=self._on_area_selected,
                on_cancelled=self._on_area_cancelled,
            )
            self._sel_windows.append(sel)
            sel.present()
        return False

    @staticmethod
    def _gdk_monitor_for_connector(display, connector):
        mons = display.get_monitors()
        for i in range(mons.get_n_items()):
            m = mons.get_item(i)
            if m.get_connector() == connector:
                return m
        return None

    def _close_selectors(self):
        for w in self._sel_windows:
            try:
                w.close()
            except Exception:
                pass
        self._sel_windows = []
        for connector, *_rest in self._monitors:
            p = os.path.join(tempfile.gettempdir(), f'frame_bg_{connector}.png')
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except OSError:
                pass

    def _on_area_selected(self, x, y, w, h):
        if self._sel_done:
            return
        self._sel_done = True
        self._close_selectors()
        self._area = (x, y, w, h)
        self.present()
        self._rec_btn.set_sensitive(True)

        delay = DELAYS[self._delay_drop.get_selected()]
        if delay > 0:
            overlay = CountdownOverlay(self._app, delay, self._start_capture)
            overlay.start()
        else:
            self._start_capture()

    def _on_area_cancelled(self):
        if self._sel_done:
            return
        self._sel_done = True
        self._close_selectors()
        self.present()
        self._rec_btn.set_sensitive(True)
        self._toast_msg('Selection cancelled')

    # ── Recording ─────────────────────────────────────────────────

    def _output_path(self):
        d = os.path.expanduser('~/Videos')
        os.makedirs(d, exist_ok=True)
        ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        fmt = self._cfg['format']
        return os.path.join(d, f'frame_{ts}.{fmt}')

    def _start_capture(self):
        x, y, w, h = self._area
        out = self._output_path()
        self._rec.start(x, y, w, h, out, self._cfg['format'],
                        framerate=self._cfg['framerate'],
                        cursor=self._cfg['cursor'],
                        callbacks={
                            'started': self._cb_started,
                            'stopped': self._cb_stopped,
                            'converting': self._cb_converting,
                            'error': self._cb_error,
                        })

    def _enter_recording_ui(self):
        self._idle.set_visible(False)
        self._rec_cluster.set_visible(True)
        self._pause_btn.set_label('Pause')
        self._timer_lbl.remove_css_class('paused')

    def _exit_recording_ui(self):
        self._rec_cluster.set_visible(False)
        self._idle.set_visible(True)

    def _cb_started(self):
        self._recording = True
        self._enter_recording_ui()
        x, y, w, h = self._area
        self._size_lbl.set_text(f'{w} × {h}')
        self._timer_secs = 0
        self._timer_lbl.set_text('0:00')
        self._timer_id = GLib.timeout_add(1000, self._tick_timer)
        self._hide_toast()
        self._emit_state()

    def _cb_converting(self):
        self._recording = False
        self._teardown()
        self._rec_btn.set_sensitive(False)
        self._toast_msg('Converting to GIF…')
        self._emit_state()

    def _cb_stopped(self, path):
        self._recording = False
        self._teardown()
        self._rec_btn.set_sensitive(True)
        self._last_saved = path
        fname = os.path.basename(path)
        self._toast_msg(f'Saved {fname}', 'done', actions=[
            ('Open', self._open_saved),
            ('Reveal', self._reveal_saved),
            ('Copy path', self._copy_saved),
        ])
        try:
            subprocess.Popen(
                ['notify-send', '-i', 'video-x-generic',
                 'Frame', f'Saved to {path}'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            pass
        self._emit_state()

    def _cb_error(self, msg):
        self._recording = False
        self._teardown()
        self._rec_btn.set_sensitive(True)
        self._toast_msg(f'Error: {msg}', 'error')
        self._emit_state()

    def _teardown(self):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        self._exit_recording_ui()

    def _tick_timer(self):
        if not self._recording:
            return False
        if self._rec.is_paused:
            return True
        self._timer_secs += 1
        m, s = divmod(self._timer_secs, 60)
        self._timer_lbl.set_text(f'{m}:{s:02d}')
        return True

    # ── Post-save actions ─────────────────────────────────────────

    def _open_saved(self):
        if self._last_saved:
            subprocess.Popen(['xdg-open', self._last_saved],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

    def _reveal_saved(self):
        if self._last_saved:
            d = os.path.dirname(self._last_saved)
            subprocess.Popen(['xdg-open', d],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

    def _copy_saved(self):
        if not self._last_saved:
            return
        clip = self.get_clipboard()
        clip.set(self._last_saved)
        self._toast_msg('Path copied to clipboard', 'done')

    def _on_close(self, _w):
        if self._recording:
            self._rec.stop()
        if self._gshortcuts:
            self._gshortcuts.stop()
        if self._dbus:
            self._dbus.unregister()
        return False


# ── Application ───────────────────────────────────────────────────────


class FrameApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.github.frame')
        self.connect('activate', self._on_activate)

    def _on_activate(self, _app):
        win = FrameWindow(self)
        win.present()
