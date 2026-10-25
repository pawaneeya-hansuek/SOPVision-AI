"""Run from project root: python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import cv2
from vision import Tracker
from production import STATIONS

STATION=STATIONS[0]
SOP=STATION['steps']

class InspectionTests(unittest.TestCase):
    def inspect(self,filename):
        cap=cv2.VideoCapture(str(ROOT/'media'/'demo'/filename))
        self.assertTrue(cap.isOpened())
        tracker=Tracker(SOP,anchor=STATION['anchor'])
        fps=cap.get(cv2.CAP_PROP_FPS)
        n=0
        while True:
            ok,frame=cap.read()
            if not ok:break
            tracker.feed(frame,n/fps)
            n+=1
        cap.release()
        return tracker.snapshot(final=True)

    def test_correct_video_passes(self):
        r=self.inspect('demo_correct.mp4')
        self.assertEqual(r['status'],'pass')
        self.assertEqual(r['verified'],2)
        self.assertTrue(all(s['status']=='passed' for s in r['steps']))

    def test_wrong_order_flags_second_color(self):
        r=self.inspect('demo_wrong_order.mp4')
        self.assertEqual(r['status'],'review')
        self.assertEqual(r['steps'][1]['status'],'out_of_order')
        self.assertEqual(r['verified'],0)

    def test_no_frame_means_missing_steps(self):
        t=Tracker(SOP,anchor=STATION['anchor'])
        r=t.snapshot(final=True)
        self.assertEqual(r['status'],'review')
        self.assertTrue(all(s['status']=='missing' for s in r['steps']))

    def test_unseen_step_is_missing_without_evidence(self):
        t=Tracker(SOP,anchor=STATION['anchor'])
        self.assertEqual(t.snapshot(final=True)['steps'][1]['status'],'missing')

if __name__=='__main__':unittest.main()
