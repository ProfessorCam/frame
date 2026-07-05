"""Tiny JSON-backed settings store for frame.

Remembers the user's last choices (format, delay, monitor, cursor, framerate)
between runs.  Kept deliberately dependency-free and defensive: a missing or
corrupt file always falls back to sane defaults rather than raising.
"""

import json
import os

DEFAULTS = {
    'format': 'gif',        # 'gif' | 'webm' | 'mp4'
    'delay': 0,             # seconds: 0 | 3 | 5 | 10
    'monitor': 0,           # index into recorder.get_monitors()
    'cursor': True,         # capture the mouse cursor
    'framerate': 30,        # 24 | 30 | 60
}

_VALID = {
    'format': {'gif', 'webm', 'mp4'},
    'delay': {0, 3, 5, 10},
    'framerate': {24, 30, 60},
}


def _config_path():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'frame', 'config.json')


class Config:
    """Dict-like settings object that persists to ~/.config/frame/config.json."""

    def __init__(self, path=None):
        self._path = path or _config_path()
        self._data = dict(DEFAULTS)
        self.load()

    # ── access ────────────────────────────────────────────────────────
    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        """Set a value (validated where we have a whitelist) and persist."""
        if key in _VALID and value not in _VALID[key]:
            return
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self.save()

    def update(self, **kwargs):
        changed = False
        for k, v in kwargs.items():
            if k in _VALID and v not in _VALID[k]:
                continue
            if self._data.get(k) != v:
                self._data[k] = v
                changed = True
        if changed:
            self.save()

    # ── persistence ───────────────────────────────────────────────────
    def load(self):
        try:
            with open(self._path, 'r', encoding='utf-8') as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        for key, default in DEFAULTS.items():
            val = raw.get(key, default)
            # Reject values that fail validation or change type
            if key in _VALID and val not in _VALID[key]:
                val = default
            if type(val) is not type(default):
                val = default
            self._data[key] = val

    def save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(self._data, fh, indent=2)
            os.replace(tmp, self._path)
        except OSError:
            pass  # Settings are best-effort; never crash the app over them.
