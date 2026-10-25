"""Build a temporary browser camera stream from the latest user clip fixture."""
from pathlib import Path
import cv2
import numpy as np

root=Path(__file__).resolve().parents[1]
cap=cv2.VideoCapture(str(root/'tests/fixtures/phone-20261022-instant.mp4'))
frames=[]
while True:
    ok,image=cap.read()
    if not ok:break
    frames.append(image)
cap.release()
assert frames
# Stop before scrolling takes the camera out of view in the screen recording.
frames=frames[:108]
height,width=frames[0].shape[:2]
blank=np.full_like(frames[0],110)
path=root/'tmp/inspection-20261022/phone-replay.y4m'
path.parent.mkdir(parents=True,exist_ok=True)
with path.open('wb') as output:
    output.write(f'YUV4MPEG2 W{width} H{height} F10:1 Ip A1:1 C420jpeg\n'.encode())
    for image in [blank]*40+frames+[frames[-1]]*50:
        output.write(b'FRAME\n'+cv2.cvtColor(image,cv2.COLOR_BGR2YUV_I420).tobytes())
print('Browser camera replay ready')
