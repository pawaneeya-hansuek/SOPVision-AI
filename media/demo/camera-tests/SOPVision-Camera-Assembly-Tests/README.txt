STATION 01 CAMERA TEST / SYNTHETIC ANIMATION, NOT REAL FOOTAGE
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
