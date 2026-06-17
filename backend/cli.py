#!/usr/bin/env python3
"""
Smile Code Agent — CLI 入口

用法::

    python cli.py
    # 或
    ./smile.sh
"""

import asyncio
import sys
from pathlib import Path

# 确保 src 在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.cli.app import main

if __name__ == "__main__":
    asyncio.run(main())
