# -*- coding: utf-8 -*-
"""CLI: python backend/image_text.py -i input.jpg -o output.jpg --target-lang zh-Hant"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.tools.image_text import main

if __name__ == "__main__":
    raise SystemExit(main())
