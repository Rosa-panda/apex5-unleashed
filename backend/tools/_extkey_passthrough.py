# ADR-031 设备侧落地：六键清回透传 255（出厂真值），M 键回归一等键。
# 写→读回→应用→保存走 MAPPER.set_targets 全流程；写前自动快照（当前=别名态 v29654）。
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import extkeys
import extkeymap

targets = {name: 255 for name, _kid in extkeys.EXT_KEYS}
res = extkeymap.extkeys.MAPPER.set_targets(targets)
print("set_targets:", res)

pad = extkeys.Pad()
st = pad.read_status()
blob = bytes(pad.read_config(st["active"]))
cur = {name: blob[13 + kid * 3] for name, kid in extkeys.EXT_KEYS}
print(f"读回: {cur}  版本={blob[225] | (blob[226] << 8)}")
assert all(v == 255 for v in cur.values()), "读回非全透传!"
print("OK：六键已全部透传，M 键不再别名任何已有键位")
