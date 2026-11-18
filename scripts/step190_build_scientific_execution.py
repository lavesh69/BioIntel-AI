from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.scientific_execution_v190 import build_step190
if __name__=='__main__': print(build_step190(ROOT))
