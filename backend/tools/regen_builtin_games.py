# 开发期工具：用本机官方适配库升级仓库内置档案（app/games/*.json）
# 只合并**事实数据**（vib 参数/进程名/official 标记）——不写入官方手感文案（版权，ADR-017/R2），
# 运行时导入器（officialimport）才带说明文案且只落在用户机器上。
# 用法：python tools/regen_builtin_games.py [官方json路径]
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

import officialimport

BUILTIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "games")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else officialimport.official_path()
    if not path:
        print("未找到官方适配库")
        return 1
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    # 现有内置档案按名字索引（去空格规范化：官方「赛博朋克 2077」vs 内置「赛博朋克2077」）
    norm = lambda s: s.replace(" ", "")
    files = {}
    for fn in os.listdir(BUILTIN_DIR):
        if fn.endswith(".json"):
            with open(os.path.join(BUILTIN_DIR, fn), "r", encoding="utf-8") as f:
                g = json.load(f)
            files[norm(g["name"])] = (fn, g)
    added = updated = 0
    for entry in entries:
        conv = officialimport.convert_entry(entry)
        if conv is None:
            continue
        name = conv["name"]
        if norm(name) in files:
            fn, g = files[norm(name)]
            exes = list(g.get("exe", []))
            for e in conv["exe"]:
                if e not in exes:
                    exes.append(e)
            g["exe"] = exes
            if conv["vib"]:
                g["vib"] = conv["vib"]
            g["official"] = True
            g["official_id"] = conv["official_id"]
            if conv["mod_only"]:
                g["mod_only"] = True
            with open(os.path.join(BUILTIN_DIR, fn), "w", encoding="utf-8") as f:
                json.dump(g, f, ensure_ascii=False, indent=2)
            updated += 1
        elif conv["vib"]:      # 官方有震动联动但仓库还没有的 → 新增（不带走官方文案）
            g = {"version": 1, "name": name, "note": "", "exe": conv["exe"],
                 "preset_id": "", "vib": conv["vib"], "official": True,
                 "official_id": conv["official_id"]}
            if conv["mod_only"]:
                g["mod_only"] = True
            import presets
            fn = presets.safe_name(name) + ".json"
            with open(os.path.join(BUILTIN_DIR, fn), "w", encoding="utf-8") as f:
                json.dump(g, f, ensure_ascii=False, indent=2)
            files[norm(name)] = (fn, g)
            added += 1
    print(f"内置档案升级完成：更新 {updated}，新增 {added}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
