# 只读诊断：所有按键无输出（2026-09-22）。三件事：
# 1) 161 状态 + 键表六键 + 全 32 键一览（看是否有键被写成 255/0）
# 2) cmd16 五开关（手柄数据开关若为 0 = 标准输出被固件静默）
# 3) gamepad HID 报文 15s 采样（按钮位/摇杆是否在动——区分「固件静默」vs「HID 不通」）
# 全程只读：161/163/16/1，不写任何命令。请在这 15 秒里随便按几个键/摇摇杆。
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import extkeys
import hid

print("=== 1) 161 状态 + 键表 ===")
pad = extkeys.Pad()
st = pad.read_status()
print(f"active slot={st['active']}")
blob = bytes(pad.read_config(st["active"]))
print(f"blob 版本={blob[225] | (blob[226] << 8)} 长度={len(blob)}")
names = {0: "up", 1: "right", 2: "down", 3: "left", 4: "a", 5: "b", 6: "select", 7: "x", 8: "y",
         9: "start", 10: "lb", 11: "rb", 12: "lt", 13: "rt", 14: "thl", 15: "thr", 16: "c", 17: "z",
         18: "m1", 19: "m2", 20: "m3", 21: "m4", 22: "lm", 23: "rm", 24: "menu", 25: "turbo", 27: "home", 28: "back"}
for kid in range(32):
    tgt = blob[13 + kid * 3]
    if tgt != 255 or kid in (4, 5, 7, 8, 10, 11, 18, 19, 20, 21, 22, 23):
        nm = names.get(kid, str(kid))
        print(f"  key{kid:<3}{nm:<8} target={tgt}")

print("=== 2) cmd16 五开关 ===")
for body in pad.exchange(extkeys.build(16), wait=0.8):
    if body[2] == 16 and len(body) > 10:
        flags = [body[5 + i] for i in range(5)]
        lbl = ["手柄数据", "私有原始", "键盘", "鼠标", "第三方"]
        print("  " + "  ".join(f"{l}={v}" for l, v in zip(lbl, flags)))

print("=== 3) gamepad HID 15s 采样（现在请按任意键/摇摇杆） ===")
dev = hid.device()
opened = False
for info in hid.enumerate(0x37D7):
    if info["usage_page"] == 1 and info["usage"] == 5:
        dev.open_path(info["path"])
        opened = True
        break
if not opened:
    print("  !! gamepad 集合没枚举到——设备可能没连/休眠")
    sys.exit(0)
last = None
n = 0
distinct = set()
t0 = time.time()
while time.time() - t0 < 15:
    r = bytes(dev.read(64, timeout_ms=100))
    if r:
        n += 1
        distinct.add(r)
        if r != last:
            print(f"  [{time.time()-t0:5.1f}s] {r.hex(' ')}")
            last = r
print(f"  共 {n} 份报告，{len(distinct)} 种内容")
