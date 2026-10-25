"""Behavioral tests for color count, sequence, speed, and final-state inspection."""
import unittest

import cv2
import numpy as np

from vision import Tracker

ANCHOR = {'color': 'green', 'roi': {'x': .06, 'y': .1, 'w': .3, 'h': .78},
          'min_area_ratio': .004}
STEPS = [
    {'id': 1, 'name': 'base', 'color': 'green', 'min_pct': .6,
     'roi': ANCHOR['roi'], 'min_area_ratio': .004, 'max_area_ratio': .45,
     'stable_seconds': .8},
    {'id': 2, 'name': 'cover', 'color': 'red', 'min_pct': .35,
     'roi': {'x': .16, 'y': .1, 'w': .42, 'h': .78},
     'min_area_ratio': .004, 'max_area_ratio': .45, 'stable_seconds': .8,
     'requires_anchor': True, 'relative_to_anchor': [.2, 3.5, -2, 2]},
]
COLORS = {'green': (30, 190, 45), 'red': (40, 40, 220),
          'blue': (220, 60, 20), 'yellow': (20, 220, 220),
          'orange': (0, 130, 255), 'purple': (200, 40, 200)}
POSITIONS = {'green': (90, 140), 'red': (190, 140), 'blue': (190, 140),
             'yellow': (290, 140), 'orange': (190, 140), 'purple': (290, 140)}


def frame(*colors, blocked=False, misplaced=None, outside=None, small=None, textured=False,
          extra_green=False):
    img = np.full((480, 640, 3), 90, np.uint8)
    if textured:
        texture = np.random.default_rng(42).integers(30, 220, (480, 260), dtype=np.uint8)
        img[:, 380:] = cv2.cvtColor(texture, cv2.COLOR_GRAY2BGR)
    for color in colors:
        x, y = POSITIONS[color]
        if color == misplaced:
            x = 270
        if color == outside:
            x = 520
        size = 12 if color == small else 65
        cv2.rectangle(img, (x, y), (x + size, y + size), COLORS[color], -1)
    if extra_green:
        cv2.rectangle(img, (430, 330), (495, 395), COLORS['green'], -1)
    if blocked:
        cv2.rectangle(img, (170, 100), (365, 310), (235, 235, 235), -1)
    return img


def tracker(steps=None):
    return Tracker(steps or STEPS, anchor=ANCHOR)


def hold(tr, start, end, *colors, **options):
    count = round((end - start) * 10)
    for index in range(count + 1):
        tr.feed(frame(*colors, **options), start + index / 10)


def install_both(tr):
    hold(tr, 0, .9, 'green')
    hold(tr, 1, 1.9, 'green', 'red')


class InstallationTrackingTests(unittest.TestCase):
    def test_color_outside_roi_counts_after_prior_step(self):
        tr = tracker()
        hold(tr, 0, .9, 'green')
        for t in (.1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0):
            found, _ = tr.feed(frame('green', 'red', outside='red'), t + 1)
        self.assertTrue(found['red']['in_target'])
        self.assertEqual(tr.snapshot(final=True)['steps'][1]['status'], 'passed')

    def test_transient_pass_through_roi_does_not_count(self):
        tr = tracker()
        tr.feed(frame('red'), 0)
        tr.feed(frame(), .1)
        tr.feed(frame(), .2)
        self.assertEqual(tr.snapshot(final=True)['verified'], 0)

    def test_first_observation_confirms_current_color_without_dwell(self):
        tr = tracker()
        tr.feed(frame('green'), 0)
        self.assertEqual(tr.snapshot()['verified'], 1)
        self.assertEqual(tr.snapshot()['steps'][0]['status'], 'passed')

    def test_green_then_red_only_completes_without_requiring_green_to_stay_visible(self):
        tr = tracker()
        tr.feed(frame('green'), 0)
        self.assertEqual(tr.snapshot()['verified'], 1)
        tr.feed(frame('red'), .08)
        self.assertEqual(tr.snapshot()['verified'], 2)
        self.assertEqual(tr.snapshot(final=True)['status'], 'pass')

    def test_new_phone_clip_updates_in_the_first_frame_of_each_color(self):
        from pathlib import Path
        cap = cv2.VideoCapture(str(Path(__file__).parent/'fixtures'/'phone-20261022-instant.mp4'))
        tr = tracker()
        index = 0
        try:
            while True:
                ok, image = cap.read()
                if not ok:
                    break
                found, _ = tr.feed(image, index / 10)
                result = tr.snapshot()
                if found['green']['count'] == 1 and len(tr.events) == 1:
                    self.assertEqual(result['verified'], 1)
                    self.assertEqual(tr.events[0]['time'], tr.events[0]['confirmed_at'])
                if len(tr.events) == 2:
                    self.assertEqual(result['verified'], 2)
                    self.assertEqual(tr.events[1]['time'], tr.events[1]['confirmed_at'])
                    self.assertEqual(tr.snapshot(final=True)['status'], 'pass')
                    break
                index += 1
            self.assertEqual(len(tr.events), 2)
        finally:
            cap.release()

    def test_wrong_anchor_relation_does_not_affect_color_count(self):
        narrow_relation = [dict(step, relative_to_anchor=[.2, 2.0, -2, 2])
                           if step['color'] == 'red' else step for step in STEPS]
        tr = tracker(narrow_relation)
        hold(tr, 0, .9, 'green')
        hold(tr, 1, 2.0, 'green', 'red', misplaced='red')
        self.assertEqual(tr.snapshot(final=True)['steps'][1]['status'], 'passed')

    def test_tiny_color_noise_is_not_counted_as_a_piece(self):
        tr = tracker()
        for index in range(10):
            tr.feed(frame('red', small='red'), index / 10)
        self.assertEqual(tr.snapshot(final=True)['steps'][1]['status'], 'missing')
        self.assertIn('0/1', tr.snapshot()['steps'][1]['reason'])

    def test_correct_position_and_size_held_stable_passes(self):
        tr = tracker()
        install_both(tr)
        result = tr.snapshot(final=True)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['verified'], 2)
        self.assertEqual(result['steps'][1]['time'], 1.0)
        self.assertEqual(result['steps'][1]['confirmed_at'], 1.0)

    def test_color_requires_exact_expected_piece_count(self):
        duplicate_color_steps = [
            dict(STEPS[0]),
            {**STEPS[0], 'id': 3, 'name': 'second green part'},
        ]
        tr = tracker(duplicate_color_steps)
        hold(tr, 0, .9, 'green')
        result = tr.snapshot(final=True)
        self.assertEqual(result['verified'], 1)
        self.assertEqual(result['steps'][0]['status'], 'passed')
        self.assertEqual(result['steps'][1]['status'], 'missing')
        self.assertEqual(result['status'], 'review')

    def test_hand_covering_a_completed_color_preserves_progress(self):
        tr = tracker()
        install_both(tr)
        tr.feed(frame('green', blocked=True), 2.0)
        tr.feed(frame('green', blocked=True), 2.7)
        result = tr.snapshot(final=True)
        self.assertEqual(result['steps'][1]['status'], 'passed')
        self.assertEqual(result['verified'], 2)

    def test_camera_moving_past_a_completed_color_preserves_completion(self):
        tr = tracker()
        install_both(tr)
        tr.feed(frame('green'), 2.0)
        tr.feed(frame('green'), 2.7)
        result = tr.snapshot(final=True)
        self.assertEqual(result['steps'][1]['status'], 'passed')
        self.assertEqual(result['verified'], 2)
        self.assertEqual(result['status'], 'pass')

    def test_wrong_order_is_latched_even_if_later_corrected(self):
        tr = tracker()
        hold(tr, 0, .9, 'red')
        hold(tr, 1, 1.9, 'green', 'red')
        result = tr.snapshot(final=True)
        self.assertEqual(result['steps'][1]['status'], 'out_of_order')
        self.assertEqual(result['status'], 'review')

    def test_simultaneous_colors_do_not_establish_order(self):
        tr = tracker()
        hold(tr, 0, .9, 'green', 'red')
        result = tr.snapshot(final=True)
        self.assertEqual(result['steps'][1]['status'], 'out_of_order')
        self.assertEqual(result['status'], 'review')

    def test_ordered_colors_confirm_in_four_fast_frames(self):
        tr = Tracker(STEPS, anchor=ANCHOR, require_stability=False)
        for second, colors in enumerate((('green',), ('green',),
                                         ('green', 'red'), ('green', 'red'))):
            tr.feed(frame(*colors), second * .05)
        result = tr.snapshot(final=True)
        self.assertEqual(result['status'], 'pass', result)
        self.assertLessEqual(result['elapsed'], .2)

    def test_camera_movement_metadata_does_not_affect_color_count_verdict(self):
        tr = tracker()
        install_both(tr)
        tr.camera_moved = True
        result = tr.snapshot(final=True)
        self.assertTrue(result['camera_moved'])
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['steps'][0]['status'], 'passed')

    def test_two_same_color_pieces_satisfy_two_steps(self):
        duplicate_color_steps = [
            dict(STEPS[0]),
            {**STEPS[0], 'id': 3, 'name': 'second green part'},
        ]
        tr = tracker(duplicate_color_steps)
        hold(tr, 0, .9, 'green')
        hold(tr, 1, 1.9, 'green', extra_green=True)
        result = tr.snapshot(final=True)
        self.assertEqual(result['verified'], 2)
        self.assertTrue(all(step['status'] == 'passed' for step in result['steps']))


if __name__ == '__main__':
    unittest.main()
