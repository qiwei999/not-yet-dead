"""Portable ninnin entrypoint; generated distribution carries lib/ninnin_core."""
from pathlib import Path
import sys
here = Path(__file__).resolve()
for candidate in (here.parents[1] / "lib", here.parents[3]):
    if (candidate / "ninnin_core").is_dir():
        sys.path.insert(0, str(candidate))
        break
from ninnin_core.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
