"""Create synthetic 18s tabletop assembly MP4 samples for testing. No real workers/video."""
import cv2
import numpy as np
from pathlib import Path
from vision import detect_colors
from db import DEFAULT_STEPS

OUT=Path(__file__).parent/'media'/'demo';OUT.mkdir(parents=True,exist_ok=True)
W,H,FPS=768,432,6
OBJECTS={
 'green':(75,160,66,66,(55,176,77)),
 'red':(175,160,66,66,(51,60,235)),
}

def write_demo(path, order):
    encoder=cv2.VideoWriter_fourcc(*'mp4v')
    v=cv2.VideoWriter(str(path),encoder,FPS,(W,H))
    if not v.isOpened():raise RuntimeError('Cannot create MP4 demo')
    for fi in range(18*FPS):
        t=fi/FPS
        img=np.full((H,W,3),(24,37,48),dtype=np.uint8)
        # worktable
        cv2.rectangle(img,(30,60),(W-30,H-35),(75,75,75),-1)
        cv2.rectangle(img,(47,75),(W-47,H-50),(231,235,237),-1)
        cv2.putText(img,'SOPVISION AI  /  ASSEMBLY DEMO',(40,38),cv2.FONT_HERSHEY_SIMPLEX,.67,(200,238,181),2)
        cv2.putText(img,'STATION A-01', (522,105),cv2.FONT_HERSHEY_SIMPLEX,.55,(48,65,79),2)
        cv2.putText(img,f'TIME: {t:05.1f}s',(520,138),cv2.FONT_HERSHEY_SIMPLEX,.55,(48,65,79),1)
        cv2.putText(img,'Fixed camera / colored parts',(515,169),cv2.FONT_HERSHEY_SIMPLEX,.39,(63,73,83),1)
        for idx,color in enumerate(order):
            if t < (2+idx*4): continue
            x,y,w,h,bgr=OBJECTS[color]
            cv2.rectangle(img,(x,y),(x+w,y+h),bgr,-1)
            cv2.rectangle(img,(x,y),(x+w,y+h),(34,53,61),2)
            cv2.putText(img,color.upper(),(x+5,y+25),cv2.FONT_HERSHEY_SIMPLEX,.46,(245,246,241),2)
        cv2.putText(img,'ORDER: '+(' > '.join(order)),(50,H-21),cv2.FONT_HERSHEY_SIMPLEX,.49,(207,227,224),1)
        v.write(img)
    v.release()

if __name__=='__main__':
    write_demo(OUT/'demo_correct.mp4',['green','red'])
    write_demo(OUT/'demo_wrong_order.mp4',['red','green'])
    print('created',[(p.name,p.stat().st_size) for p in OUT.glob('*.mp4')])
