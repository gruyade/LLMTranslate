"""ポータブル実行用エントリーポイント（PyInstaller / 直接実行両対応）"""
import sys
import os

# srcパッケージをパスに追加（直接実行時）
sys.path.insert(0, os.path.dirname(__file__))

from src.main import main

if __name__ == "__main__":
    main()
