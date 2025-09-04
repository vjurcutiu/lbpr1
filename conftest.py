# 66696c657374617274 ./conftest.py
from pathlib import Path
import sys

# Ensure project root is on sys.path before tests import modules
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
