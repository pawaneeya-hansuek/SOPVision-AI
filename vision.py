"""Color-component counting for assembly inspection."""
from __future__ import annotations

import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import Any

HSV = {
    'green': [((36, 65, 55), (85, 255, 255))],
    # Low-saturation orange/red skin was counted as extra red parts on phone video.
    'red': [((0, 140, 60), (8, 255, 255)), ((169, 140, 60), (179, 255, 255))],
    'blue': [((91, 85, 50), (132, 255, 255))],
    'yellow': [((18, 75, 75), (37, 255, 255))],
    'orange': [((8, 100, 80), (20, 255, 255))],
    'purple': [((133, 60, 50), (165, 255, 255))],
}

LIVE_SAMPLE_MS = 80
VIDEO_SAMPLE_FPS = 15


def detect_colors(frame: np.ndarray, steps: list[dict], anchor: dict | None = None) -> dict[str, dict]:
    """Count visible color components across the full frame."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    colors = {step['color'] for step in steps}
    result = {}
    frame_area = max(1, frame.shape[0] * frame.shape[1])
    minimum_area = max(25, round(frame_area * 0.005))
    for color in colors:
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for low, high in HSV[color]:
            mask |= cv2.inRange(hsv, np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        objects = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < minimum_area:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            objects.append({'bbox': [x, y, width, height], 'area': area})
        objects.sort(key=lambda item: item['area'], reverse=True)
        area = sum(item['area'] for item in objects)
        bbox = objects[0]['bbox'] if objects else None
        result[color] = {
            'visible': bbox is not None,
            'count': len(objects),
            'objects': objects,
            'coverage': round(100.0 * area / frame_area, 2),
            'bbox': bbox,
            'area': area,
        }
    return result
@dataclass
class Tracker:
    steps: list[dict]
    anchor: dict | None = None
    configuration_version: int = 1
    require_stability: bool = True
    prior_steps: list[dict] = field(default_factory=list)
    prior_verified: bool = False
    prior_confirmed_at: float | None = None
    prior_counts: dict[str, int] = field(default_factory=dict)
    recent: dict[str, dict] = field(default_factory=dict)
    observed: dict[str, float] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    frames: int = 0
    elapsed: float = 0.0
    camera_moved: bool = False
    latest_counts: dict[str, int] = field(default_factory=dict)
    candidate_step: int | None = None
    candidate_since: float | None = None
    candidate_frames: int = 0
    violation_step_id: int | None = None
    future_candidate_color: str | None = None
    future_candidate_frames: int = 0
    previous_counts: dict[str, int] = field(default_factory=dict)
    count_frames: dict[str, int] = field(default_factory=dict)

    def feed(self, frame: np.ndarray, seconds: float):
        found = detect_colors(frame, self.prior_steps + self.steps, self.anchor)
        now = max(self.elapsed, float(seconds))
        self.elapsed = now
        self.frames += 1
        prior_required = {}
        for step in self.prior_steps:
            color=step['color']
            prior_required[color]=prior_required.get(color,0)+1
        self.prior_counts={color:found[color]['count'] for color in prior_required}
        if self.prior_steps and not self.prior_verified and all(
                self.prior_counts[color]>=count for color,count in prior_required.items()):
            self.prior_verified=True
            self.prior_confirmed_at=round(now,3)
        expected_counts: dict[str, int] = {}
        for step in self.steps:
            expected_counts[step['color']] = expected_counts.get(step['color'], 0) + 1
        self.latest_counts = {color: found[color]['count'] for color in expected_counts}
        for color, count in self.latest_counts.items():
            self.count_frames[color] = self.count_frames.get(color, 0) + 1 if self.previous_counts.get(color) == count else 1
            self.previous_counts[color] = count
        for color, count in self.latest_counts.items():
            item = self.recent.setdefault(color, {})
            item['current_count'] = count
            item['bbox'] = found[color]['bbox']
            if count:
                item['last_seen'] = now

        newly_passed = []
        if self.prior_steps and not self.prior_verified:
            return found, newly_passed
        confirmed_count = len(self.events)
        if self.violation_step_id is None and confirmed_count < len(self.steps):
            step = self.steps[confirmed_count]
            color = step['color']
            future_color = next((later['color'] for later in self.steps[confirmed_count + 1:]
                                 if later['color'] != color
                                 and self.latest_counts.get(later['color'], 0) == expected_counts[later['color']]), None)
            if future_color:
                if self.future_candidate_color == future_color:
                    self.future_candidate_frames += 1
                else:
                    self.future_candidate_color = future_color
                    self.future_candidate_frames = 1
                if self.future_candidate_frames >= 2:
                    self.violation_step_id = next(later['id'] for later in self.steps[confirmed_count + 1:]
                                                   if later['color'] == future_color)
                    self.candidate_step = None
                    self.candidate_frames = 0
            elif any(self.latest_counts[c] > expected for c, expected in expected_counts.items()
                     if not (expected == 1 and c in self.observed)):
                self.future_candidate_color = None
                self.future_candidate_frames = 0
                self.candidate_step = None
                self.candidate_frames = 0
            else:
                self.future_candidate_color = None
                self.future_candidate_frames = 0
                required_count = sum(previous['color'] == color
                                     for previous in self.steps[:confirmed_count + 1])
                if self.latest_counts.get(color, 0) == required_count:
                    if self.candidate_step != step['id']:
                        self.candidate_step = step['id']
                        self.candidate_since = now
                        self.candidate_frames = 1
                    else:
                        self.candidate_frames += 1
                    if self.candidate_frames >= 1:
                        event = {
                            'step_id': step['id'], 'name': step['name'], 'color': color,
                            'time': round(self.candidate_since if self.candidate_since is not None else now, 3),
                            'confirmed_at': round(now, 3), 'simultaneous': False,
                        }
                        self.events.append(event)
                        newly_passed.append(step)
                        self.observed.setdefault(color, event['time'])
                        self.recent[color] = {'state': 'passed', 'current_count': self.latest_counts[color],
                                              'last_seen': now, 'first_seen': event['time']}
                        self.candidate_step = None
                        self.candidate_since = None
                        self.candidate_frames = 0
                elif required_count < self.latest_counts.get(color, 0) <= expected_counts[color]:
                    self.violation_step_id = step['id']
                    self.candidate_step = None
                    self.candidate_since = None
                    self.candidate_frames = 0
                else:
                    self.candidate_step = None
                    self.candidate_since = None
                    self.candidate_frames = 0

        for color, detection in found.items():
            expected = expected_counts.get(color, 0)
            detection.update({'expected_count': expected,
                              'count_matches': detection['count'] == expected,
                              'in_target': detection['count'] == expected,
                              'installed_position': detection['count'] == expected,
                              'outside_target': False})
        return found, newly_passed

    def prior_check(self):
        required={}
        for step in self.prior_steps:
            required[step['color']]=required.get(step['color'],0)+1
        rows=[]
        for step in self.prior_steps:
            color=step['color'];count=self.prior_counts.get(color,0)
            passed=self.prior_verified or count>=required[color]
            rows.append({**step,'count':count,'expected_count':required[color],
                         'status':'passed' if passed else 'missing',
                         'reason':('ตรวจพบงานจากสเตชั่นก่อนหน้าแล้ว' if passed else f'ยังไม่พบสี {color} จากสเตชั่นก่อนหน้า')})
        return {'required':bool(rows),'passed':not rows or self.prior_verified,
                'verified':sum(row['status']=='passed' for row in rows),'total':len(rows),
                'confirmed_at':self.prior_confirmed_at,'steps':rows}

    def snapshot(self, final: bool = False, seconds: float | None = None) -> dict[str, Any]:
        statuses = []
        events_by_id = {event['step_id']: event for event in self.events}
        expected_counts: dict[str, int] = {}
        for step in self.steps:
            expected_counts[step['color']] = expected_counts.get(step['color'], 0) + 1
        required_by_index: dict[int, int] = {}
        running_counts: dict[str, int] = {}
        for index, step in enumerate(self.steps):
            running_counts[step['color']] = running_counts.get(step['color'], 0) + 1
            required_by_index[index] = running_counts[step['color']]

        for index, step in enumerate(self.steps):
            color = step['color']
            item = self.recent.get(color, {})
            count = self.latest_counts.get(color, 0)
            total = expected_counts[color]
            required = required_by_index[index]
            event = events_by_id.get(step['id'])
            reason = f'พบสี {color} {count}/{total} ชิ้น'
            sequence_violation = step['id'] == self.violation_step_id
            if sequence_violation:
                state, reason = 'out_of_order', f'ลำดับผิด: พบสี {color} ก่อนขั้นตอนก่อนหน้า'
            elif self.prior_steps and not self.prior_verified:
                state, reason = ('missing' if final else 'waiting'), 'รอตรวจสีจากสเตชั่นก่อนหน้าให้ครบก่อน'
            elif event and total == 1:
                # A completed color step stays completed when the operator's
                # hand or the next QR replaces it in the camera view.
                state, reason = 'passed', f'พบสี {color} ตามลำดับแล้ว'
            elif count > total:
                state, reason = 'uncertain', f'จำนวนสี {color} เกินกำหนด ({count}/{total})'
            elif not event and count > required:
                state, reason = 'uncertain', f'จำนวนสี {color} ข้ามขั้นตอน ({count}/{required})'
            elif event and count >= required:
                state, reason = 'passed', f'พบสี {color} จำนวน {required} ชิ้นแล้ว'
            elif event and count < required:
                state, reason = 'missing', f'สี {color} เหลือ {count}/{required} ชิ้น'
            elif final:
                state = 'missing'
            elif index == len(self.events) and self.candidate_step == step['id']:
                state, reason = 'verifying', f'ยืนยันสี {color} {count}/{required} ชิ้น'
            elif index < len(self.events):
                state = 'missing'
            else:
                state = 'waiting'
            statuses.append({
                'id': step['id'], 'name': step['name'], 'color': color,
                'time': event.get('time') if event else item.get('first_seen'),
                'confirmed_at': event.get('confirmed_at') if event else None,
                'state': state, 'status': state, 'reason': reason,
                'sequence_violation': sequence_violation,
                'ambiguous_sequence': False,
                'temporarily_hidden': bool(event and count < required),
                'last_seen': item.get('last_seen'), 'bbox': item.get('bbox'),
                'roi': step.get('roi'),
            })
        problems = sum(step['status'] in ('out_of_order', 'uncertain', 'missing') for step in statuses)
        verified = sum(step['status'] == 'passed' for step in statuses)
        all_passed = verified == len(statuses) and bool(statuses) and self.prior_check()['passed']
        return {
            'steps': statuses, 'events': self.events, 'verified': verified,
            'total': len(statuses), 'issues': problems,
            'elapsed': round(self.elapsed, 1), 'frames': self.frames,
            'configuration_version': self.configuration_version,
            'prior_check': self.prior_check(),
            'inspection_mode': 'fast',
            'camera_moved': self.camera_moved,
            'status': 'pass' if final and all_passed else 'review' if final else 'running',
        }


def jpeg(frame: np.ndarray, quality=76) -> bytes:
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError('ไม่สามารถเข้ารหัสภาพได้')
    return buf.tobytes()


def annotated(frame: np.ndarray, found: dict, steps: list[dict] | None = None) -> np.ndarray:
    output = frame.copy()
    bgr = {'green': (85, 210, 100), 'red': (75, 90, 240), 'blue': (225, 135, 45),
           'yellow': (50, 225, 245), 'orange': (0, 166, 255), 'purple': (180, 95, 185)}
    for color, data in found.items():
        color_value = bgr.get(color, (255, 255, 255))
        for component in data.get('objects', []):
            x, y, width, height = component['bbox']
            cv2.rectangle(output, (x, y), (x + width, y + height), color_value, 2)
        if data.get('bbox'):
            x, y, _, _ = data['bbox']
            cv2.putText(output, f'{color.upper()} {data.get("count", 0)}',
                        (x, max(14, y - 7)), cv2.FONT_HERSHEY_SIMPLEX, .52,
                        color_value, 2)
    return output
