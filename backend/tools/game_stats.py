# 内置游戏库适配分布盘点（只读统计，不改数据）
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import gameprofiles  # noqa: E402

d = gameprofiles.builtin_games_dir()
games = []
for fn in sorted(os.listdir(d)):
    if fn.endswith(".json"):
        with open(os.path.join(d, fn), encoding="utf-8") as f:
            games.append(json.load(f))

total = len(games)
has_vib = [g for g in games if g.get("vib")]
has_preset = [g for g in games if g.get("preset_id")]
both = [g for g in games if g.get("vib") and g.get("preset_id")]
only_vib = [g for g in has_vib if not g.get("preset_id")]
only_preset = [g for g in has_preset if not g.get("vib")]
neither = [g for g in games if not g.get("vib") and not g.get("preset_id")]

print(f"总条目: {total}")
print(f"带 vib 震动联动: {len(has_vib)}")
print(f"带 preset 扳机预设: {len(has_preset)}")
print(f"两者都有: {len(both)}")
print(f"仅 vib: {len(only_vib)}")
print(f"仅 preset: {len(only_preset)}")
print(f"啥都没有(纯清单占位): {len(neither)}")
print()
print("=== 预设引用分布 ===")
c = collections.Counter(g.get("preset_id") for g in games if g.get("preset_id"))
for k, v in c.most_common():
    print(f"  {k}: {v} 个游戏")
print()
print("=== vib 参数分布（去重签名） ===")
sig = collections.Counter()
for g in has_vib:
    v = g["vib"]
    s = (v.get("filter"), v.get("scale"), v.get("stroke"), v.get("press"), v.get("strength"), v.get("freq"))
    sig[s] += 1
print(f"不同参数签名数: {len(sig)}（共 {len(has_vib)} 条 vib）")
for s, n in sig.most_common(10):
    print(f"  filter={s[0]} scale={s[1]} stroke={s[2]} press={s[3]} strength={s[4]} freq={s[5]}: {n} 个游戏")
print()
print("=== 完全无适配的条目示例（前8） ===")
for g in neither[:8]:
    print(f"  {g['name']} (official={g.get('official', False)})")
