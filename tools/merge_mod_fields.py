# -*- coding: utf-8 -*-
"""官方 Mod 字段并入内置游戏档案（ADR-025，幂等可重跑）。
从本机空间站 adapterTriggerGames.json 读 ModDownLoadUrl 等字段，按 official_id
写进内置 of-*.json 的 mod 字段。mod 本体不进仓库——只存 CDN 直链（与封面图同策略）。
用法：python tools/merge_mod_fields.py [--dry]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(HERE, "..", "backend", "app", "games")
OFFICIAL = r"C:\Program Files\Flydigi Space Station\Configs\Controller\Trigger\adapterTriggerGames.json"

# 保留官方原始字段名（后续逆向/对照方便）
KEEP = {"ModDownLoadUrl": "url", "ModName": "name", "Version": "version",
        "ModStartType": "start_type", "ProcessGameName": "process",
        "ProcessGameModName": "mod_process", "ExeName": "game_exe", "ModPath": "path"}


def main():
    dry = "--dry" in sys.argv
    official = json.load(open(OFFICIAL, encoding="utf-8"))
    by_id = {g["Id"]: g for g in official if g.get("ModDownLoadUrl")}
    print(f"官方带 Mod 下载源: {len(by_id)} 条")

    merged = skipped = 0
    for fn in sorted(os.listdir(GAMES)):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(GAMES, fn)
        g = json.load(open(p, encoding="utf-8"))
        oid = g.get("official_id")
        if oid not in by_id:
            continue
        mod = {KEEP[k]: by_id[oid][k] for k in KEEP if by_id[oid].get(k) not in (None, "")}
        if g.get("mod") == mod:
            skipped += 1
            continue
        g["mod"] = mod
        if not dry:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(g, f, ensure_ascii=False, indent=2)
        merged += 1
        print(f"  {'[dry] ' if dry else ''}{fn}: {mod.get('name')} v{mod.get('version')}")
    print(f"合并 {merged} 条，已最新跳过 {skipped} 条")


if __name__ == "__main__":
    main()
