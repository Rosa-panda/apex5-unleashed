# 探针：20 秒内监听 vendor 接口 0xEF 帧位图变化，诊断拓展键检测丢失。
# 跑之前请按一遍 M1-M6。
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import hid

NAMES = {18: "M1", 19: "M2", 20: "M3", 21: "M4", 22: "M5", 23: "M6"}

dev = None
for d in hid.enumerate(0x37D7, 0x2501):
    if d.get("usage_page") == 0xFFA0:
        dev = hid.device()
        dev.open_path(d["path"])
        dev.set_nonblocking(False)
        break
if dev is None:
    raise SystemExit("vendor 接口未找到")

print("监听 20s，请按 M1-M6 …", flush=True)
end = time.time() + 20
last = None
ef_count = 0
other = {}
while time.time() < end:
    r = bytes(dev.read(64, timeout_ms=50))
    if not r:
        continue
    if r[0] == 0x04 and len(r) > 3 and r[1] == 0x5A and r[2] == 0xA5:
        cmd = r[3]
        if cmd == 0xEF:
            ef_count += 1
            if len(r) >= 15:
                cur = r[11] | (r[12] << 8) | (r[13] << 16) | (r[14] << 24)
                if cur != last:
                    last = cur
                    ks = [n for i, n in NAMES.items() if cur >> i & 1]
                    print(f"  位图变化: {cur:08x}  拓展键={ks or '无'}", flush=True)
        else:
            other[cmd] = other.get(cmd, 0) + 1
    else:
        other[-1] = other.get(-1, 0) + 1

print(f"\n0xEF 帧总数={ef_count}  其他帧={other}")
