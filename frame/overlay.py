"""Full-screen countdown overlay shown before a delayed recording starts.

Draws a large translucent number centred on the chosen monitor, counting down
to zero, then fires ``on_finished``.  Purely visual – it reuses the same
DrawingArea + Cairo approach as the selection window.
"""

import gi
gi.require_version('Gtk', '4.0')

import cairo
from gi.repository import Gdk, GLib, Gtk


class CountdownOverlay(Gtk.Window):
    def __init__(self, app, seconds, on_finished):
        super().__init__(application=app)
        self._remaining = seconds
        self._on_finished = on_finished
        self._tick_id = None

        self.set_decorated(False)
        self.fullscreen()
        # Let clicks fall through visually is not possible for a top-level, but
        # the overlay only lives for a few seconds and captures nothing useful.
        try:
            self.set_cursor(Gdk.Cursor.new_from_name('none'))
        except Exception:
            pass

        self._canvas = Gtk.DrawingArea()
        self._canvas.set_draw_func(self._draw)
        self.set_child(self._canvas)

        esc = Gtk.ShortcutController()
        esc.set_scope(Gtk.ShortcutScope.GLOBAL)
        esc.add_shortcut(Gtk.Shortcut.new(
            Gtk.KeyvalTrigger.new(Gdk.KEY_Escape, 0),
            Gtk.CallbackAction.new(lambda *_: self._cancel())))
        self.add_controller(esc)

        self._cancelled = False

    def start(self):
        self.present()
        self._tick_id = GLib.timeout_add(1000, self._tick)

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._finish()
            return False
        self._canvas.queue_draw()
        return True

    def _finish(self):
        self._teardown()
        self.close()
        if not self._cancelled:
            self._on_finished()

    def _cancel(self):
        self._cancelled = True
        self._finish()

    def _teardown(self):
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = None

    def _draw(self, _area, cr, width, height):
        # Dim the screen
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.paint()

        cx, cy = width / 2, height / 2
        num = str(self._remaining)

        # Soft rounded disc behind the number
        r = min(width, height) * 0.11
        cr.set_source_rgba(0.10, 0.10, 0.12, 0.85)
        cr.arc(cx, cy, r, 0, 2 * 3.14159265)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.12)
        cr.set_line_width(2)
        cr.arc(cx, cy, r, 0, 2 * 3.14159265)
        cr.stroke()

        # The digit
        cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(r * 1.2)
        ext = cr.text_extents(num)
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.move_to(cx - ext.width / 2 - ext.x_bearing,
                   cy - ext.height / 2 - ext.y_bearing)
        cr.show_text(num)

        # Hint
        cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(16)
        hint = 'Recording starts soon  •  Esc to cancel'
        hext = cr.text_extents(hint)
        cr.set_source_rgba(1, 1, 1, 0.6)
        cr.move_to(cx - hext.width / 2, cy + r + 40)
        cr.show_text(hint)
