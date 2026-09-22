# 修复冒烟误写（2026-09-22）：冒烟 POST 经 extkeys.Pad 直连真机，把 m1 写成了 255。
# 恢复六键 = 老行为映射（m1→视图6，其余不变），走 ADR-019 验证过的 164/165→162→166。
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import extkeys

TARGETS = {"m1": 6, "m2": 9, "m3": 10, "m4": 11, "lm": 16, "rm": 17}
res = extkeys.MAPPER.set_targets(TARGETS)
print("写回:", res)
cur = extkeys.MAPPER.read_mapping()
for e in cur:
    print(f"  {e['name']}: {e['target']} ({e['target_name']})")
