"""Optional system-wide shortcuts via xdg-desktop-portal ``GlobalShortcuts``.

This is the only Wayland-correct way for a normal app to get truly global
hotkeys (ones that fire even when another window is focused).  It is entirely
best-effort:

* If the portal or the ``GlobalShortcuts`` interface is missing (older
  desktops), :meth:`GlobalShortcuts.start` returns False and does nothing.
* On GNOME the shortcuts are surfaced in Settings ▸ Keyboard ▸ (the app), where
  the user assigns/confirms the actual key combos.  We only *suggest* triggers.

The GNOME Shell extension is the primary always-available control; these
hotkeys are a bonus for users who prefer the keyboard.

Portal reference: https://flatpak.github.io/xdg-desktop-portal/docs/
"""

from gi.repository import Gio, GLib

PORTAL_BUS = 'org.freedesktop.portal.Desktop'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
GS_IFACE = 'org.freedesktop.portal.GlobalShortcuts'
REQUEST_IFACE = 'org.freedesktop.portal.Request'

# Shortcut ids handed back in the Activated signal.
TOGGLE_PAUSE = 'frame-toggle-pause'
STOP = 'frame-stop'


class GlobalShortcuts:
    """Registers frame's global shortcuts through the desktop portal.

    Args:
        connection: a ``Gio.DBusConnection`` on the session bus, or None.
        on_activated: callable ``(shortcut_id: str) -> None``.
    """

    def __init__(self, connection, on_activated):
        self._conn = connection
        self._on_activated = on_activated
        self._session_handle = None
        self._token_seq = 0
        self._activated_sub = 0
        self._request_subs = []

    # ── availability ──────────────────────────────────────────────────
    def available(self):
        if self._conn is None:
            return False
        try:
            self._conn.call_sync(
                PORTAL_BUS, PORTAL_PATH, 'org.freedesktop.DBus.Properties',
                'Get', GLib.Variant('(ss)', (GS_IFACE, 'version')),
                GLib.VariantType('(v)'), Gio.DBusCallFlags.NONE, 1500, None)
            return True
        except GLib.Error:
            return False

    # ── helpers ───────────────────────────────────────────────────────
    def _sender_token(self):
        # ':1.234' -> '1_234' : the sender part of a portal request path.
        name = self._conn.get_unique_name() or ':1.0'
        return name[1:].replace('.', '_')

    def _next_token(self, prefix):
        self._token_seq += 1
        return f'{prefix}_{self._token_seq}'

    def _subscribe_response(self, token, callback):
        """Subscribe to the Response of a portal request we're about to make.

        We predict the request object path from the handle token so there's no
        race between the method returning and the signal arriving.
        """
        path = (f'/org/freedesktop/portal/desktop/request/'
                f'{self._sender_token()}/{token}')

        def handler(_c, _s, _p, _i, _sig, params, _d):
            self._conn.signal_unsubscribe(sub_id)
            if sub_id in self._request_subs:
                self._request_subs.remove(sub_id)
            # Never let a portal quirk crash the app – hotkeys are optional.
            try:
                response, results = params.unpack()
                callback(response, results)
            except Exception:
                pass

        sub_id = self._conn.signal_subscribe(
            PORTAL_BUS, REQUEST_IFACE, 'Response', path, None,
            Gio.DBusSignalFlags.NONE, handler, None)
        self._request_subs.append(sub_id)

    # ── flow ──────────────────────────────────────────────────────────
    def start(self):
        """Create a portal session and bind the shortcuts. Returns True if the
        portal is present and the flow was kicked off."""
        if not self.available():
            return False

        self._activated_sub = self._conn.signal_subscribe(
            PORTAL_BUS, GS_IFACE, 'Activated', PORTAL_PATH, None,
            Gio.DBusSignalFlags.NONE, self._on_activated_signal, None)

        req_token = self._next_token('frame_cs')
        sess_token = self._next_token('frame_sess')
        self._subscribe_response(req_token, self._on_session_created)
        try:
            self._conn.call_sync(
                PORTAL_BUS, PORTAL_PATH, GS_IFACE, 'CreateSession',
                GLib.Variant('(a{sv})', [{
                    'handle_token': GLib.Variant('s', req_token),
                    'session_handle_token': GLib.Variant('s', sess_token),
                }]),
                GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, 2000, None)
        except GLib.Error:
            self.stop()
            return False
        return True

    def _on_session_created(self, response, results):
        if response != 0:
            return
        self._session_handle = results.get('session_handle')
        if not self._session_handle:
            return
        self._bind_shortcuts()

    def _bind_shortcuts(self):
        # Native Python values – the single outer GLib.Variant() below builds
        # the whole 'a(sa{sv})' structure.  (Pre-wrapping this as its own
        # Variant and nesting it is what caused the earlier crash.)  The a{sv}
        # dict values must themselves be Variants – that's the 'v'.
        shortcuts = [
            (TOGGLE_PAUSE, {
                'description': GLib.Variant('s', 'frame: Pause / Resume recording'),
                'preferred_trigger': GLib.Variant('s', 'CTRL+ALT+p'),
            }),
            (STOP, {
                'description': GLib.Variant('s', 'frame: Stop recording'),
                'preferred_trigger': GLib.Variant('s', 'CTRL+ALT+s'),
            }),
        ]
        req_token = self._next_token('frame_bind')
        self._subscribe_response(req_token, lambda _r, _res: None)
        try:
            self._conn.call_sync(
                PORTAL_BUS, PORTAL_PATH, GS_IFACE, 'BindShortcuts',
                GLib.Variant('(oa(sa{sv})sa{sv})', (
                    self._session_handle, shortcuts, '',
                    {'handle_token': GLib.Variant('s', req_token)})),
                GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, 2000, None)
        except GLib.Error:
            pass

    def _on_activated_signal(self, _c, _s, _p, _i, _sig, params, _d):
        session_handle, shortcut_id = params.unpack()[0], params.unpack()[1]
        if self._session_handle and session_handle != self._session_handle:
            return
        try:
            self._on_activated(shortcut_id)
        except Exception:
            pass

    def stop(self):
        if self._conn is None:
            return
        for sub in self._request_subs:
            self._conn.signal_unsubscribe(sub)
        self._request_subs = []
        if self._activated_sub:
            self._conn.signal_unsubscribe(self._activated_sub)
            self._activated_sub = 0
        if self._session_handle:
            try:
                self._conn.call_sync(
                    PORTAL_BUS, self._session_handle,
                    'org.freedesktop.portal.Session', 'Close',
                    None, None, Gio.DBusCallFlags.NONE, 1000, None)
            except GLib.Error:
                pass
            self._session_handle = None
