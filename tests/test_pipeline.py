"""Unit tests for frame.recorder.build_pipeline (pure string construction)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frame.recorder import build_pipeline


def have_all(_name):
    return True


def have_none(_name):
    return False


class PipelineTest(unittest.TestCase):
    def test_gif_uses_mkv_intermediate_and_x264(self):
        pipe, target, out = build_pipeline(
            'gif', 42, 640, 480, 30, '/tmp/out.gif', have=have_all)
        self.assertTrue(target.endswith('.tmp.mkv'))
        self.assertIn('x264enc', pipe)
        self.assertIn('matroskamux', pipe)
        self.assertIn('path=42', pipe)
        self.assertEqual(out, '/tmp/out.gif')

    def test_gif_fallback_without_x264(self):
        pipe, target, out = build_pipeline(
            'gif', 1, 640, 480, 30, '/tmp/out.gif', have=have_none)
        self.assertIn('vp8enc', pipe)
        self.assertNotIn('x264enc', pipe)

    def test_framerate_threaded_into_caps(self):
        pipe, _t, _o = build_pipeline(
            'webm', 1, 800, 600, 60, '/tmp/o.webm', have=have_all)
        self.assertIn('framerate=60/1', pipe)

    def test_mp4_pins_explicit_dimensions(self):
        pipe, target, out = build_pipeline(
            'mp4', 1, 1280, 720, 24, '/tmp/o.mp4', have=have_all)
        self.assertIn('width=1280,height=720', pipe)
        self.assertIn('framerate=24/1', pipe)
        self.assertIn('mp4mux', pipe)
        self.assertEqual(target, '/tmp/o.mp4')

    def test_mp4_falls_back_to_webm_without_x264(self):
        pipe, target, out = build_pipeline(
            'mp4', 1, 1280, 720, 30, '/tmp/o.mp4', have=have_none)
        self.assertTrue(target.endswith('.webm'))
        self.assertEqual(out, target)
        self.assertIn('vp8enc', pipe)

    def test_webm_prefers_vp9(self):
        pipe, _t, _o = build_pipeline(
            'webm', 1, 640, 480, 30, '/tmp/o.webm', have=have_all)
        self.assertIn('vp9enc', pipe)

    def test_filesink_targets_output(self):
        pipe, target, _o = build_pipeline(
            'webm', 1, 640, 480, 30, '/tmp/o.webm', have=have_all)
        self.assertIn(f'filesink location="{target}"', pipe)

    def test_pipeline_has_pause_valve(self):
        pipe, _t, _o = build_pipeline(
            'webm', 1, 640, 480, 30, '/tmp/o.webm', have=have_all)
        self.assertIn('valve name=wpvalve', pipe)


if __name__ == '__main__':
    unittest.main()
