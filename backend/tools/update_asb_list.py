# ASB 游戏清单导入（ADR-022）：ApexSenseBridge 的 211 款 DS 原生自适应扳机游戏 → 内置档案。
# 幂等：重跑先清旧 asb-*.json 再写。官方条目优先（exe/规范化名命中即跳过）。
# 跑法：python tools/update_asb_list.py [本地.json 路径]   （不给路径则走代理拉云端）
import json
import os
import re
import sys
import urllib.request

SRC_URL = "https://raw.githubusercontent.com/ReynArts/ApexSenseBridge/stable/data/supported_games.json"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
import gameprofiles  # noqa: E402


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def fetch(path=None):
    if path:
        with open(path, "r", encoding="utf-8-sig") as f:   # 容忍 BOM（PS Out-File 产物）
            return json.load(f)
    req = urllib.request.Request(SRC_URL, headers={"User-Agent": "apex5-unleashed"})
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    handlers = [urllib.request.ProxyHandler({"https": proxy})] if proxy else []
    with urllib.request.build_opener(*handlers).open(req, timeout=30) as r:
        return json.load(r)


def main():
    src = fetch(sys.argv[1] if len(sys.argv) > 1 else None)
    games = src.get("games", [])
    out_dir = gameprofiles.builtin_games_dir()

    # 清旧
    removed = 0
    for fn in os.listdir(out_dir):
        if fn.startswith("asb-") and fn.endswith(".json"):
            os.remove(os.path.join(out_dir, fn))
            removed += 1

    # 官方/既有条目的占位集（exe 与规范化名）
    existing = gameprofiles.GameProfiles.__new__(gameprofiles.GameProfiles)
    taken_exe, taken_name = set(), set()
    for g in gameprofiles.GameProfiles._load(existing, out_dir, True).values():
        taken_name.add(norm(g["name"]))
        for e in g.get("exe", []):
            taken_exe.add(norm(e))

    wrote, skipped = 0, 0
    for g in games:
        if not (g.get("adaptiveTriggers") or g.get("hapticFeedback")):
            continue
        title = g.get("title", "").strip()
        exes = [e.lower() for e in (g.get("executables") or [])]
        if not title:
            continue
        if norm(title) in taken_name or any(norm(e) in taken_exe for e in exes):
            skipped += 1
            continue
        feats = []
        if g.get("adaptiveTriggers"):
            feats.append("自适应扳机")
        if g.get("hapticFeedback"):
            feats.append("触觉反馈")
        note = (f"原生支持 DualSense {'/'.join(feats)}（ASB/PCGamingWiki 清单）。"
                "事件级效果需 ApexSenseBridge 桥；本工具提供震动联动兜底。")
        entry = {
            "version": 1, "name": title,
            "en": title if title.isascii() else "",
            "exe": exes, "preset_id": "", "note": note,
            "image": g.get("iconUrl", ""),
            "asb": True, "source": "asb-list",
            "steam_appid": g.get("steamAppId"),
        }
        safe = norm(title) or "game"
        with open(os.path.join(out_dir, f"asb-{safe}.json"), "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        wrote += 1

    print(f"云端清单 {len(games)} 条 → 写入 {wrote}，与官方重合跳过 {skipped}，清理旧 {removed}")
    print(f"档案目录: {out_dir}")


if __name__ == "__main__":
    main()
