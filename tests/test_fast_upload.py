"""Check actual compressed video via the production upload analyzer."""
from unittest.mock import patch
import cv2
from main import analyze_video
from production import STATIONS
from test_fast_tracking import frame


def analyze(tmp_path, frames):
    path=tmp_path/'fast.avi'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),20,(640,480))
    assert writer.isOpened()
    for colors in frames:writer.write(frame(*colors))
    writer.release()
    with patch('main.remember_evidence',return_value='/test-evidence.jpg'):
        return analyze_video(path,'fast-upload-test',{**STATIONS[0],'version':0})


def test_upload_requires_stable_color_count(tmp_path):
    result=analyze(tmp_path,[('green',)]*24+[('green','red')]*24)
    assert result['status']=='pass'
    assert result['verified']==2


def test_upload_tolerates_one_hidden_sample(tmp_path):
    result=analyze(tmp_path,[('green',)]*20+[('green',),(),('green',)]
                    +[('green','red')]*24)
    assert result['status']=='pass'


def test_fast_wrong_order_upload_is_rejected(tmp_path):
    result=analyze(tmp_path,[('red',)]*24+[('green','red')]*24)
    assert result['status']=='review'
    assert result['steps'][1]['status']=='out_of_order'
