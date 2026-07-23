"""コマンドの入口。第3回で `hitblow` コマンドがここ（main）を呼ぶ。"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from .game import play

def open_rule() -> None:
    """ルール説明PDFを開く。"""
    pdf_path = (
        Path(__file__).resolve().parent
        / "howtoplay"
        / "ForJupyterHub.pdf"
    )

    if not pdf_path.is_file():
        print(f"【警告】ルールPDFが見つかりません: {pdf_path}")
        return

    try:
        # 1. Windowsローカル（最優先）
        if sys.platform == "win32":
            os.startfile(str(pdf_path))

        # 2. Mac
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(pdf_path)])

        # 3. Linux系（JupyterHub + code-server含む）
        elif shutil.which("code") is not None:
            subprocess.Popen(["code", str(pdf_path)])

        else:
            subprocess.Popen(["xdg-open", str(pdf_path)])

    except Exception as e:
        print(f"【警告】PDFを開けませんでした: {e}")

def main():
    """ルールを表示し、可能であればゲームを開始する。"""
    # JupyterHub/サーバー環境のチェック
    if (
        "JUPYTERHUB_USER" in os.environ 
        or "JPY_PARENT_PID" in os.environ
        or "DISPLAY" not in os.environ and sys.platform != "win32"
    ):
        print("\n" + "="*50)
        print("【動作環境エラー】")
        print("JupyterHubではゲーム画面（GUI）を表示できません。")
        print("以下のURLからhitblow.exeをダウンロードしてください")
        print("https://github.com/b242456/hitblow/releases/tag/0.1.0_exe")
        print("="*50)
        open_rule()
        return

    # 環境に問題がなければ、従来の通りゲームを開始
    play()