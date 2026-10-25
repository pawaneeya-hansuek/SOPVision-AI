"""Isolated browser test server; never uses production DB or media."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.test-deps'))
TMP=ROOT/'.test-access-ui';TMP.mkdir(exist_ok=True)
import db
db.DB=TMP/'browser.db'
import production,cameras
production.RECORDINGS=TMP/'recordings';production.RECORDINGS.mkdir(exist_ok=True)
production.EVIDENCE=TMP/'evidence';production.EVIDENCE.mkdir(exist_ok=True)
cameras.MEDIA=TMP
import main,uvicorn
if __name__=='__main__':uvicorn.run(main.app,host='127.0.0.1',port=8765,log_level='warning')
