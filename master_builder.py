import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

biointel_dir = SRC / "biointel"

print("--- Master Step Builder Starting ---")

for sub in sorted(biointel_dir.iterdir()):
    if not sub.is_dir():
        continue
    mod_name = f"biointel.{sub.name}"
    try:
        m = importlib.import_module(mod_name)
    except Exception:
        continue

    for attr in dir(m):
        if attr.startswith("build_") or attr in ("build_all", "generate_all", "build"):
            fn = getattr(m, attr)
            if callable(fn):
                try:
                    print(f"Calling {mod_name}.{attr}...")
                    fn(ROOT)
                    print(f"  --> {mod_name}.{attr} PASSED!")
                except Exception as exc:
                    print(f"  --> {mod_name}.{attr} ERROR: {exc}")

print("--- Master Step Builder Completed ---")
