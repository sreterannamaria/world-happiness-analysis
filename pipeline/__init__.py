"""Reproducible pipeline for the BINA case study (World Happiness Report).

Run from the repository root:

    python -m pipeline.build_database   # data/ -> bina.sqlite
    python -m pipeline.analyze          # bina.sqlite -> results/
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "bina.sqlite"
RESULTS_DIR = ROOT / "results"
