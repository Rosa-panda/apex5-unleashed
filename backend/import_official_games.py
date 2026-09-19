# 一次性：官方 93 游戏清单 → 内置游戏档案 JSON（ADR-014/015 归一化的第一步）
# 数据源：空间站云端 API 响应缓存 %TEMP%\flydigi_games.json（本机已抓取）
import json
import os
import re
import tempfile
import time

SRC = os.path.join(tempfile.gettempdir(), "flydigi_games.json")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "games")

data = json.load(open(SRC, encoding="utf-8"))["data"]
print(f"official games: {len(data)}")

n = 0
for g in data:
    exes = [p for p in (g.get("processGameNames") or []) if p]
    exes += [g["exeName"]] if g.get("exeName") else []
    exes += [g["modName"]] if g.get("modName") else []
    if not exes:
        print("skip (no exe key):", g.get("gameName"))
        continue
    exes = sorted({(e if e.endswith(".exe") else e + ".exe").lower() for e in exes})
    gid = "of-" + re.sub(r"[^a-z0-9]+", "-", (g.get("enGameName") or g.get("gameName") or str(g.get("gid"))).lower()).strip("-")[:40]
    prof = {
        "version": 1,
        "name": g.get("gameName") or g.get("enGameName"),
        "en": g.get("enGameName") or "",
        "note": f"官方适配清单 · {g.get('platform', '')}",
        "exe": exes,
        "preset_id": "",
        "image": g.get("imagePath") or "",
        "source": "official-list",
        "imported_at": time.strftime("%Y-%m-%d"),
    }
    with open(os.path.join(OUT, gid + ".json"), "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=1)
    n += 1
print(f"written: {n} profiles -> {OUT}")
