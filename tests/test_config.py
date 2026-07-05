"""Unit tests for frame.config — persistence and validation."""

import json
import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frame.config import Config, DEFAULTS


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.path = os.path.join(self._dir, 'sub', 'config.json')

    def tearDown(self):
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_defaults_when_missing(self):
        cfg = Config(self.path)
        for key, val in DEFAULTS.items():
            self.assertEqual(cfg[key], val)

    def test_set_persists_and_roundtrips(self):
        cfg = Config(self.path)
        cfg.set('format', 'mp4')
        cfg.set('delay', 5)
        cfg.set('framerate', 60)
        cfg.set('cursor', False)
        # Reload from disk with a fresh instance
        cfg2 = Config(self.path)
        self.assertEqual(cfg2['format'], 'mp4')
        self.assertEqual(cfg2['delay'], 5)
        self.assertEqual(cfg2['framerate'], 60)
        self.assertFalse(cfg2['cursor'])

    def test_invalid_values_rejected(self):
        cfg = Config(self.path)
        cfg.set('format', 'avi')       # not in whitelist
        cfg.set('delay', 7)            # not in whitelist
        cfg.set('framerate', 12)       # not in whitelist
        self.assertEqual(cfg['format'], DEFAULTS['format'])
        self.assertEqual(cfg['delay'], DEFAULTS['delay'])
        self.assertEqual(cfg['framerate'], DEFAULTS['framerate'])

    def test_corrupt_file_falls_back(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as fh:
            fh.write('{not valid json')
        cfg = Config(self.path)
        self.assertEqual(cfg['format'], DEFAULTS['format'])

    def test_partial_and_bad_types_repaired(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as fh:
            json.dump({'format': 'webm', 'delay': 'soon', 'monitor': 2}, fh)
        cfg = Config(self.path)
        self.assertEqual(cfg['format'], 'webm')        # kept
        self.assertEqual(cfg['delay'], DEFAULTS['delay'])  # wrong type -> default
        self.assertEqual(cfg['monitor'], 2)            # kept
        self.assertEqual(cfg['cursor'], DEFAULTS['cursor'])  # missing -> default

    def test_update_multiple(self):
        cfg = Config(self.path)
        cfg.update(format='webm', framerate=24, monitor=1)
        cfg2 = Config(self.path)
        self.assertEqual(cfg2['format'], 'webm')
        self.assertEqual(cfg2['framerate'], 24)
        self.assertEqual(cfg2['monitor'], 1)


if __name__ == '__main__':
    unittest.main()
