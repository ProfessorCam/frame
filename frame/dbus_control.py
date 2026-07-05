"""A small D-Bus control interface for frame.

Exported on the application's own bus name (``com.github.frame``) so external
agents – the GNOME Shell top-bar extension and the global-shortcut handler –
can drive recording without the pill window having focus.

Interface ``com.github.frame.Control`` at ``/com/github/frame/Control``:

* methods ``Pause`` / ``Resume`` / ``TogglePause`` / ``Stop`` / ``GetState``
* signal  ``StateChanged(b recording, b paused)``
* props   ``Recording`` / ``Paused`` (read-only)

Everything is best-effort: if there is no session-bus connection (e.g. the app
was launched with D-Bus disabled) registration is skipped silently and the
in-pill controls keep working.
"""

from gi.repository import Gio, GLib

BUS_NAME = 'com.github.frame'
OBJECT_PATH = '/com/github/frame/Control'
IFACE = 'com.github.frame.Control'

INTROSPECTION_XML = """
<node>
  <interface name="com.github.frame.Control">
    <method name="Pause"/>
    <method name="Resume"/>
    <method name="TogglePause"/>
    <method name="Stop"/>
    <method name="GetState">
      <arg type="b" name="recording" direction="out"/>
      <arg type="b" name="paused" direction="out"/>
    </method>
    <signal name="StateChanged">
      <arg type="b" name="recording"/>
      <arg type="b" name="paused"/>
    </signal>
    <property name="Recording" type="b" access="read"/>
    <property name="Paused" type="b" access="read"/>
  </interface>
</node>
"""


class DBusControl:
    """Registers the control object on a D-Bus connection.

    Args:
        connection: a ``Gio.DBusConnection`` (usually
            ``Gio.Application.get_dbus_connection()``), or None.
        handlers: dict with callables ``pause``, ``resume``, ``toggle``, ``stop``.
        state_provider: callable returning ``(recording: bool, paused: bool)``.
    """

    def __init__(self, connection, handlers, state_provider):
        self._conn = connection
        self._handlers = handlers
        self._state = state_provider
        self._reg_id = 0
        node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        self._iface_info = node.lookup_interface(IFACE)

    # ── lifecycle ─────────────────────────────────────────────────────
    def register(self):
        """Register the object. Returns True on success."""
        if self._conn is None or self._reg_id:
            return False
        try:
            self._reg_id = self._conn.register_object(
                OBJECT_PATH, self._iface_info,
                self._on_method_call, self._on_get_property, None)
        except GLib.Error:
            self._reg_id = 0
        return bool(self._reg_id)

    def unregister(self):
        if self._conn and self._reg_id:
            self._conn.unregister_object(self._reg_id)
            self._reg_id = 0

    # ── dispatch ──────────────────────────────────────────────────────
    def _on_method_call(self, _conn, _sender, _path, _iface, method,
                        params, invocation):
        try:
            if method == 'Pause':
                self._handlers['pause']()
            elif method == 'Resume':
                self._handlers['resume']()
            elif method == 'TogglePause':
                self._handlers['toggle']()
            elif method == 'Stop':
                self._handlers['stop']()
            elif method == 'GetState':
                rec, pau = self._state()
                invocation.return_value(GLib.Variant('(bb)', (rec, pau)))
                return
            else:
                invocation.return_dbus_error(
                    'org.freedesktop.DBus.Error.UnknownMethod', method)
                return
        except Exception as e:  # never let a caller crash the app
            invocation.return_dbus_error(
                'com.github.frame.Error.Failed', str(e))
            return
        invocation.return_value(None)

    def _on_get_property(self, _conn, _sender, _path, _iface, prop):
        rec, pau = self._state()
        if prop == 'Recording':
            return GLib.Variant('b', rec)
        if prop == 'Paused':
            return GLib.Variant('b', pau)
        return None

    # ── signals ───────────────────────────────────────────────────────
    def emit_state(self):
        """Broadcast the current (recording, paused) state."""
        if self._conn is None or not self._reg_id:
            return
        rec, pau = self._state()
        try:
            self._conn.emit_signal(
                None, OBJECT_PATH, IFACE, 'StateChanged',
                GLib.Variant('(bb)', (rec, pau)))
            self._conn.emit_signal(
                None, OBJECT_PATH, 'org.freedesktop.DBus.Properties',
                'PropertiesChanged',
                GLib.Variant('(sa{sv}as)', (
                    IFACE,
                    {'Recording': GLib.Variant('b', rec),
                     'Paused': GLib.Variant('b', pau)},
                    [])))
        except GLib.Error:
            pass
