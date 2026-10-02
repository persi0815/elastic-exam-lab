#!/usr/bin/env python3
"""Regenerate fixtures and all six sets, preserving the required build order."""
from pathlib import Path
import subprocess,sys
here=Path(__file__).resolve().parent
for name in ('generate_v2.py','generate_e.py','build_catalog.py','extend_catalog.py','extend_catalog_e.py','generate_f.py'):
    subprocess.run([sys.executable,str(here/name)],check=True,cwd=here.parent)
