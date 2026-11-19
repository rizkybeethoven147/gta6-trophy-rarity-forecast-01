"""Entry point for the make.fun gta6-trophy-rarity-forecast-01 submission.

Reads each *.in case and writes the matching *.out file. All forecasting
logic lives in model.py.
"""
import json
import os
import sys
from pathlib import Path

# The grader runs with -P, so add this file's directory to import model from it.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from model import forecast_case

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        result = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(result, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        print(f"wrote {path.stem}.out ({len(result['trophies'])} trophies)")


if __name__ == "__main__":
    main()
