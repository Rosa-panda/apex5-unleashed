# 手柄固件重启（cmd29）+ 重连后复核（2026-09-22 全按键无输出修复尝试）。
# 背景：12:18:44 手柄曾重新枚举（官方服务突发实锤），疑固件僵死；档案/键表/XInput 均健康。
# 步骤：发 29 → 等 10s → 161 状态 → 键表六键 → HID 流活性。
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import extkeys
import hid

pad = extkeys.Pad()
print("发 cmd29 重启…")
acks = pad.exchange(extkeys.build(29), wait=1.0)
print("ACK:", [bytes(b).hex() for b in acks][:2])

print("等 10s 重枚举…")
time.sleep(10)

infos = hid.enumerate(0x37D7)
print(f"重枚举: {len(infos)} 个接口")
if not infos:
    print("!! 设备没回来")
    sys.exit(1)

print("161 状态…")
pad2 = extkeys.Pad()
st = pad2.read_status()
print(f"active slot={st['active']}")
blob = bytes(pad2.read_config(st["active"]))
print(f"版本={blob[225] | (blob[226] << 8)}")
for name, kid in extkeys.EXT_KEYS:
    tgt = blob[13 + kid * 3]
    print(f"  {name}: {tgt} ({extkeys.TARGET_NAMES.get(tgt, '?')})")

print("HID 流 5s 采样…")
dev = hid.device()
for info in infos:
    if info["usage_page"] == 1 and info["usage"] == 5:
        dev.open_path(info["path"])
        break
n, t0 = 0, time.time()
while time.time() - t0 < 5:
    if dev.read(64, timeout_ms=100):
        n += 1
print(f"  5s 收 {n} 份报告")
print("完成——请用户回来后按几个键验证。")
