"""Animated two-part assembly scenes for Station 01; not real assembly footage."""
from pathlib import Path
import cv2
import numpy as np
from vision import Tracker
from production import STATIONS

OUT = Path(__file__).parent / 'media' / 'demo' / 'camera-tests'
OUT.mkdir(parents=True, exist_ok=True)
W, H, FPS, SECONDS = 960, 540, 12, 32


def text(img, value, xy, size=.6, color=(54, 54, 54), thick=1):
    cv2.putText(img, value, xy, cv2.FONT_HERSHEY_SIMPLEX, size, color, thick, cv2.LINE_AA)


def qr_image(job):
    qr = cv2.QRCodeEncoder_create().encode(job)
    qr = cv2.copyMakeBorder(qr, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    return cv2.resize(qr, (300, 300), interpolation=cv2.INTER_NEAREST)


def part(img, kind, x, y):
    if kind == 'green':
        width, height = 350, 190
        top, side = (65, 165, 68), (43, 113, 46)
    else:
        width, height = 235, 95
        top, side = (48, 51, 220), (32, 36, 159)
    cv2.rectangle(img, (x+9, y+14), (x+width+9, y+height+14), (164, 164, 164), -1)
    cv2.rectangle(img, (x, y+12), (x+width, y+height+12), side, -1)
    cv2.rectangle(img, (x, y), (x+width, y+height), top, -1)
    cv2.rectangle(img, (x, y), (x+width, y+height), (65, 65, 65), 2)
    cv2.line(img, (x+5, y+4), (x+width-5, y+4), (195, 195, 195), 2)
    for px in [x+16, x+width-16]:
        for py in [y+16, y+height-16]:
            cv2.circle(img, (px, py), 5, (64, 64, 64), -1)
    text(img, 'BASE' if kind == 'green' else 'COVER', (x+width//2-36, y+height//2+8), .6, (235,235,235), 2)


def frame(t, good, qr, job):
    img = np.full((H,W,3), (240,240,240), np.uint8)
    cv2.rectangle(img, (0,0), (W,76), (42,42,42), -1)
    text(img, 'SOPVISION / STATION 01', (25,30), .65, (245,245,245), 2)
    text(img, job+'  |  SYNTHETIC ASSEMBLY ANIMATION', (25,57), .43, (210,210,210))
    text(img, f'{t:04.1f}s', (850,40), .6, (240,240,240))
    if t < 6:
        img[100:400,330:630] = cv2.cvtColor(qr,cv2.COLOR_GRAY2BGR)
        text(img,'SCAN QR / SELECT STATION 01', (234,437), .7)
        text(img,'Pause here. Start camera inspection before resuming.',(185,474),.54)
        return img
    cv2.rectangle(img,(45,103),(915,486),(216,216,216),-1)
    cv2.rectangle(img,(55,112),(905,475),(228,228,228),-1)
    if t < 10:
        text(img,'CAMERA READY', (345,260), .9)
        text(img,'Keep the whole work area in view.',(265,303),.65)
        text(img,'Sequence starts at 10 seconds.',(280,340),.6)
    order = ['green','red'] if good else ['red','green']
    placements={}
    hand=None
    for i,kind in enumerate(order):
        start=10+i*9
        if t < start: continue
        progress=min(1,(t-start)/3)
        smooth=progress*progress*(3-2*progress)
        tx,ty=(305,224) if kind=='green' else (362,258)
        x=int(tx-520*(1-smooth));y=ty
        placements[kind]=(x,y)
        if t<start+4.2:
            hand=(x-23,y+45,int(220*max(0,(t-start-3)/1.2)))
    # Fixed layer order: cover sits above the base even in the incorrect sequence.
    for kind in ['green','red']:
        if kind in placements: part(img,kind,*placements[kind])
    if hand:
        x,y,retreat=hand;x-=retreat
        cv2.rectangle(img,(max(55,x-280),y+14),(max(55,x-12),y+74),(178,178,178),-1)
        cv2.ellipse(img,(x,y+42),(54,36),0,0,360,(194,194,194),-1)
        for k in range(3):
            cv2.ellipse(img,(x+37,y+18+k*19),(32,8),0,0,360,(202,202,202),-1)
    if t>=10:
        label='Place the green base' if t<19 and good or t>=19 and not good else 'Fit the red cover'
        text(img,label if t<26 else 'Assembly complete. Finish inspection in SOPVision.',(110,515),.64)
    return img


def build(good):
    job='JOB-CAMERA-PASS-001' if good else 'JOB-CAMERA-FAIL-001'
    name='assembly_correct' if good else 'assembly_wrong_order'
    qr=qr_image(job)
    assert cv2.QRCodeDetector().detectAndDecode(qr)[0]==job
    cv2.imwrite(str(OUT/(name+'_QR.png')),qr)
    path=OUT/(name+'.webm')
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'VP80'),FPS,(W,H))
    if not writer.isOpened(): raise RuntimeError('WebM encoder unavailable')
    for i in range(FPS*SECONDS): writer.write(frame(i/FPS,good,qr,job))
    writer.release()
    results=[]
    # Inspect decoded video with sampling matching the fast web camera (~0.1 seconds).
    # Repeat with moderate blur/downsizing to check tolerance, without claiming a phone test.
    for simulated in [False,True]:
        cap=cv2.VideoCapture(str(path));tr=Tracker(STATIONS[0]['steps']);i=0
        while True:
            ok,img=cap.read()
            if not ok:break
            if i%max(1,round(FPS/10))==0:
                if simulated:
                    img=cv2.resize(img,(640,360));img=cv2.GaussianBlur(img,(5,5),1)
                tr.feed(img,i/FPS)
            i+=1
        cap.release();result=tr.snapshot(final=True)
        assert result['status']==('pass' if good else 'review'),result
        results.append(result)
    print(path.name,results[-1]['status'],[(s['color'],s['status']) for s in results[-1]['steps']])
    return path


if __name__=='__main__':
    import zipfile
    for good in [True,False]:build(good)
    guide='''STATION 01 CAMERA TEST / SYNTHETIC ANIMATION, NOT REAL FOOTAGE
Two-part plastic box: green base then red cover. 32 seconds, 960x540.

1. Play one clip on a computer or second screen. Pause on its QR code (0-6s).
2. On the phone open SOPVision over trusted HTTPS. Choose QR Production Flow,
   Station 01 and operator. Scan the displayed QR, or type the printed job code.
3. Start inspection, allow the camera and aim at the screen. Resume the clip.
4. Keep the entire work area visible, phone steady, glare low, screen brightness high.
5. At the end press Finish in the website. Correct clip should pass 2/2.
   Wrong clip places red before green: it should flag order and block handoff.

The phone needs to have its camera/HTTPS setup working already. This package
does not connect a phone to the server. Camera QR scanning depends on browser
BarcodeDetector support; if unavailable, type the job code manually.

Use fresh job IDs for repeat tests if the previous attempt was completed or blocked.
Jobs: JOB-CAMERA-PASS-001 / JOB-CAMERA-FAIL-001.
This pair matches QR Station 01 only (two steps); general Video Upload expects
the separate default four-color SOP, so it will flag missing blue/yellow steps.
Detection checks color presence and order, not whether a cover is actually fitted.
Both files passed decoded-video and blur/downsize software tests. A physical
phone filming a screen has NOT been tested; results depend on lighting and framing.
'''
    (OUT/'README.txt').write_text(guide,encoding='utf-8')
    with zipfile.ZipFile(OUT/'SOPVision-Camera-Assembly-Tests.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.iterdir():
            if p.suffix in ['.webm','.png','.txt']:z.write(p,p.name)
