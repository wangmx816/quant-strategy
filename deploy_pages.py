#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键构建看板并同步 gh-pages 分支（GitHub Pages 部署源）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> None:
    run([sys.executable, "build_dashboard.py"])

    run(["git", "add", "index.html", "assets/backtest.js", "build_dashboard.py"])
    status = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if status.returncode != 0:
        run(["git", "commit", "-m", "Update dashboard and sync pages"])

    run(["git", "push", "origin", "main"])

    run(["git", "checkout", "gh-pages"])
    try:
        run(["git", "checkout", "main", "--", "index.html", "assets"])
        run(["git", "add", "index.html", "assets"])
        status = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
        if status.returncode != 0:
            run(["git", "commit", "-m", "Sync pages from main"])
        run(["git", "push", "origin", "gh-pages"])
    finally:
        run(["git", "checkout", "main"])

    print("Done. Pages: https://wangmx816.github.io/quant-strategy/")


if __name__ == "__main__":
    main()
