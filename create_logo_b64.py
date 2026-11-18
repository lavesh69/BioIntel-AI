import base64
from pathlib import Path

src = Path("src/biointel/ui/assets/biointel_logo.png")
b64 = base64.b64encode(src.read_bytes()).decode("ascii")
dest = Path("src/biointel/ui/logo_b64.py")
dest.write_text(f'LOGO_BASE64 = "data:image/png;base64,{b64}"\n', encoding="utf-8")
print("logo_b64.py created successfully with length:", len(b64))
