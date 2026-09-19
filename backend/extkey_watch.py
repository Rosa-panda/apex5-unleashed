# 拓展键物理状态监听（ADR-019 终极发现）：vendor 0xEF 体感流 = 32 键实时位图
# 官方 OperatorDataParser.IsButtonPressed：NewXInput 键位图在（从 5A 数起的）
# data[11..14]，keyId 16-23（=M1-M6 拓展键）在 data[13] —— 与固件映射无关的物理按压！
# 原始 HID 报告（含 report id 0x04）：位图在 r[12..15]，拓展键在 r[15]。
# 用法：python extkey_watch.py [秒数，默认 120]   按 M2 / 菜单键对照，看哪个 bit 翻转
import sys
import time

import hid

SECS = int(sys.argv[1]) if sys.argv[1:] else 120
KEY_NAMES = {18: "M1", 19: "M2", 20: "M3", 21: "M4", 22: "LM/M5", 23: "RM/M6",
             24: "Fn", 25: "Turbo", 9: "start", 6: "select", 27: "home", 0: "up",
             1: "right", 2: "down", 3: "left", 4: "a", 5: "b", 7: "x", 8: "y",
             10: "lb", 11: "rb", 12: "lt", 13: "rt", 14: "thl", 15: "thr"}

dev = None
for d in hid.enumerate(0x37D7, 0x2501):
    if d.get("usage_page") == 0xFFA0:
        dev = hid.device()
        dev.open_path(d["path"])
        break
if not dev:
    print("vendor 接口未找到")
    sys.exit(1)

print(f"监听 0xEF 键位图 {SECS}s —— 按 M2 和 菜单键 对照（每行=一次状态变化）")
print("位图字节（含 report id 的原始偏移 r[12..15]）:")
last = None
end = time.time() + SECS
n = 0
while time.time() < end:
    try:
        r = bytes(dev.read(64, timeout_ms=50))
    except Exception as e:
        print(f"接口异常: {e}")
        break
    if len(r) < 16 or r[1] != 0x5A or r[2] != 0xA5 or r[3] != 0xEF:
        continue
    n += 1
    cur = r[12:16]
    if cur != last:
        last = cur
        bits = []
        for byte_i in range(4):
            for bit in range(8):
                if cur[byte_i] & (1 << bit):
                    kid = byte_i * 8 + bit
                    bits.append(f"{KEY_NAMES.get(kid, kid)}(id{kid})")
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] r12-15={cur.hex(' ')}  按下: {', '.join(bits) if bits else '(无)'}", flush=True)
print(f"结束，共 {n} 帧")
