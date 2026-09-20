# 一次性清理（2026-09-20，用户定则：默认不走扳机预设）：
# 内置档案一律不携带 preset_id——预设绑定是用户的显式决定，不随软件出厂。
# 官方适配照旧（vib 震动联动参数不受影响）。幂等，可重复跑。
import glob
import json
import os

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "games")
n = 0
for f in glob.glob(os.path.join(D, "*.json")):
    with open(f, encoding="utf-8") as fh:
        g = json.load(fh)
    if g.pop("preset_id", None) is not None:
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(g, fh, ensure_ascii=False, indent=2)
        n += 1
        print("cleared:", os.path.basename(f), g["name"])
print(f"done, {n} files changed")
