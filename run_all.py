"""
Run the pipeline in order, stopping if any step fails.

    python run_all.py --scope providence        # Providence, census tracts
    python run_all.py --scope ri                # all of Rhode Island
    python run_all.py --scope both              # both scopes
    python run_all.py --scope ri --level bg     # block groups instead of tracts
    python run_all.py --year 2016               # a different ACS vintage
    python run_all.py --scope ri --start 5      # resume from step 5
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

STEPS = [  # (number, script, only for this scope)
    (1, "01_fetch_osm.py", None),
    (2, "02_fetch_acs.py", None),
    (3, "03_wards.py", "providence"),
    (4, "04_build_units.py", None),
    (5, "05_analyze.py", None),
    (6, "06_figures.py", None),
]

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--scope", choices=["providence", "ri", "both"], default="providence")
parser.add_argument("--level", choices=["tract", "bg"], default="tract")
parser.add_argument("--year", type=int, default=2024)
parser.add_argument("--start", type=int, default=1)
args = parser.parse_args()

here = Path(__file__).resolve().parent
scopes = ["providence", "ri"] if args.scope == "both" else [args.scope]

for scope in scopes:
    env = {**os.environ, "ALPR_SCOPE": scope, "ALPR_LEVEL": args.level,
           "ALPR_ACS_YEAR": str(args.year)}
    run = f"{scope}_{args.level}_{args.year}"
    for number, script, only in STEPS:
        if number < args.start or (only and only != scope):
            continue
        print(f"\n{'=' * 64}\n▶ [{run}] {script}\n{'=' * 64}")
        if subprocess.run([sys.executable, str(here / script)], cwd=here, env=env).returncode:
            sys.exit(f"\nStopped: {script} failed.")
    print(f"\nFinished {run}: results in output/{run}/")