#!/usr/bin/python3
"""Entry point for frame."""

import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gst', '1.0')

from gi.repository import Gst
Gst.init(None)

from frame.app import FrameApp

def main():
    app = FrameApp()
    return app.run(sys.argv)

if __name__ == '__main__':
    sys.exit(main())
