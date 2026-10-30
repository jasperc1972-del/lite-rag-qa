"""
conftest.py — pytest 共用設定

把專案根目錄加入匯入路徑，讓測試可以直接 import chunker、loaders 等模組。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
