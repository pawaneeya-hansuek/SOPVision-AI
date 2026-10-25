"""Compatibility entry on port 8001; forwards to the single backend on port 8000."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'.test-deps'))
import uvicorn
if __name__=='__main__':
    uvicorn.run('mobile_gateway:app',host='127.0.0.1',port=8001,
                timeout_graceful_shutdown=5,access_log=False)
