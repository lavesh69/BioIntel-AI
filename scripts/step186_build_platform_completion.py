from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from biointel.platform_completion_v186 import build_step186
if __name__=='__main__':print(build_step186(ROOT))
