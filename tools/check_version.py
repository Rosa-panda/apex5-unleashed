# 版本一致性检查（CI 与本地均可跑）：VERSION 是唯一真相源。
# 目前登记的同步位置：frontend/package.json（界面显示已走 /api/version，不在此列）。
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fail = False

with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
    ver = f.read().strip()

pkg = os.path.join(ROOT, "frontend", "package.json")
with open(pkg, encoding="utf-8") as f:
    pj = json.load(f).get("version", "")
print(f"VERSION               = {ver}")
print(f"frontend/package.json = {pj}")
if pj != ver:
    print("✗ frontend/package.json 与 VERSION 不一致（改版本请只改 VERSION，再同步 package.json）")
    fail = True

sys.exit(1 if fail else 0)
