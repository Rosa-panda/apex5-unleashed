# 只复核不发命令：161 状态 + 键表六键 + HID 流活性（2026-09-22 修复验证）
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import extkeys
import hid

print("161 状态…")
pad = extkeys.Pad()
st = pad.read_status()
print(f"active slot={st['active']}")
blob = bytes(pad.read_config(st["active"]))
print(f"版本={blob[225] | (blob[226] << 8)}")
for name, kid in extkeys.EXT_KEYS:
    tgt = blob[13 + kid * 3]
    print(f"  {name}: {tgt} ({extkeys.TARGET_NAMES.get(tgt, '?')})")

print("cmd16 五开关…")
for body in pad.exchange(extkeys.build(16), wait=0.8):
    if body[2] == 16 and len(body) > 10:
        flags = [body[5 + i] for i in range(5)]
        print("  " + "  ".join(f"{l}={v}" for l, v in
              zip(["手柄数据", "私有原始", "键盘", "鼠标", "第三方"], flags)))

print("HID 流 5s 采样（请按任意键/摇摇杆）…")
dev = hid.device()
opened = False
for info in hid.enumerate(0x37D7):
    if info["usage_page"] == 1 and info["usage"] == 5:
        dev.open_path(info["path"])
        opened = True
        break
if not opened:
    print("  !! gamepad 集合没枚举到")
    sys.exit(1)
n, last = 0, None
t0 = time.time()
while time.time() - t0 < 5:
    r = bytes(dev.read(64, timeout_ms=100))
    if r:
        n += 1
        if r != last:
            print(f"  [{time.time()-t0:4.1f}s] {r.hex(' ')}")
            last = r
print(f"  5s 收 {n} 份报告")
