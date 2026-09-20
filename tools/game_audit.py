# -*- coding: utf-8 -*-
"""游戏库全量审计：按 UI 角标逻辑给每个内置档案分档，列出无角标档案。
用法：python tools/game_audit.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(HERE, "..", "backend", "app", "games")

# 与 GameLibrary.tsx 角标渲染逻辑同源（保持同步！）
def classify(g):
    if g.get("asb"):
        if not g.get("vib"):
            return "DS原生(旧兜底)"
        return "DS转官·通用" if g.get("vib_source") == "asb-seed-fallback" else "DS转官"
    if g.get("vib"):
        return "题材适配" if g.get("vib_source") == "genre-seed" else "官方适配"
    if g.get("mod_only"):
        return "Mod条目"
    if g.get("preset_id"):
        return "预设适配"
    return "!!无角标"


def main():
    cats = {}
    plain = []
    for fn in sorted(os.listdir(GAMES)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(GAMES, fn), "r", encoding="utf-8") as f:
            g = json.load(f)
        c = classify(g)
        cats[c] = cats.get(c, 0) + 1
        if c == "!!无角标":
            plain.append((fn, g.get("name"), g.get("en"), g.get("exe"),
                          bool(g.get("official")), g.get("official_id")))
    print("分档统计：")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n}")
    print(f"\n无角标档案 {len(plain)} 条：")
    for fn, name, en, exe, off, oid in plain:
        print(f"  {fn}\n    name={name} en={en} official={off} official_id={oid} exe={exe}")


if __name__ == "__main__":
    main()
