"""Unit tests for frame.dbus_control (interface definition + dispatch).

These avoid a live bus: they validate the introspection XML parses and that the
method-call handler routes to the right callables and returns correct state,
using a fake D-Bus invocation object.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
from gi.repository import Gio, GLib

from frame.dbus_control import DBusControl, INTROSPECTION_XML, IFACE


class FakeInvocation:
    def __init__(self):
        self.returned = 'UNSET'
        self.error = None

    def return_value(self, variant):
        self.returned = variant

    def return_dbus_error(self, name, msg):
        self.error = (name, msg)


class DBusControlTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.state = (False, False)
        self.ctl = DBusControl(
            connection=None,
            handlers={
                'pause': lambda: self.calls.append('pause'),
                'resume': lambda: self.calls.append('resume'),
                'toggle': lambda: self.calls.append('toggle'),
                'stop': lambda: self.calls.append('stop'),
            },
            state_provider=lambda: self.state,
        )

    def test_introspection_xml_parses_and_has_interface(self):
        node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        self.assertIsNotNone(node.lookup_interface(IFACE))

    def test_interface_declares_expected_methods(self):
        node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        iface = node.lookup_interface(IFACE)
        names = {m.name for m in iface.methods}
        self.assertEqual(
            names, {'Pause', 'Resume', 'TogglePause', 'Stop', 'GetState'})

    def _invoke(self, method, params=None):
        inv = FakeInvocation()
        self.ctl._on_method_call(
            None, ':1.1', '/p', IFACE, method, params, inv)
        return inv

    def test_methods_route_to_handlers(self):
        for m, expected in [('Pause', 'pause'), ('Resume', 'resume'),
                            ('TogglePause', 'toggle'), ('Stop', 'stop')]:
            self._invoke(m)
        self.assertEqual(self.calls, ['pause', 'resume', 'toggle', 'stop'])

    def test_getstate_returns_current_state(self):
        self.state = (True, True)
        inv = self._invoke('GetState')
        self.assertEqual(inv.returned.unpack(), (True, True))

    def test_unknown_method_returns_error(self):
        inv = self._invoke('Nope')
        self.assertIsNotNone(inv.error)

    def test_get_property_returns_state(self):
        self.state = (True, False)
        rec = self.ctl._on_get_property(None, ':1.1', '/p', IFACE, 'Recording')
        pau = self.ctl._on_get_property(None, ':1.1', '/p', IFACE, 'Paused')
        self.assertTrue(rec.unpack())
        self.assertFalse(pau.unpack())


if __name__ == '__main__':
    unittest.main()
