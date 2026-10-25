"""Launch mobile gateway with local optional transport dependencies."""
from pathlib import Path
import sys,runpy
root=Path(__file__).resolve().parent
deps=root/'.test-deps'
if deps.is_dir():sys.path.insert(0,str(deps))
if __name__=='__main__':runpy.run_path(str(root/'start_mobile.py'),run_name='__main__')
