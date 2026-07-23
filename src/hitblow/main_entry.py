"""PyInstaller用エントリーポイント。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from hitblow.cli import main

if __name__ == "__main__":
    main()