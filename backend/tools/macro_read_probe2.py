# 探针：验证 172 是否请求驱动（每次请求回一包）。连发 N 次，记录每包 (total, index)。
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import extkeys

pad = extkeys.Pad()
st = pad.read_status()
cfg = st["active"]
print(f"active cfg={cfg}")

seen = []
for i in range(6):
    bodies = pad.exchange(extkeys.build(172, bytes([cfg, 20])), wait=1.0)
    for b in bodies:
        if b[2] == 172:
            seen.append((b[3], b[4]))
            print(f"req{i}: total={b[3]} idx={b[4]} data={bytes(b[6:26]).hex()}")

print(f"\n共收到 {len(seen)} 包, idx 序列: {[x[1] for x in seen]}")
