# 全接口抓包：监听八5 全部 HID 集合，40 秒内按拓展键，定位原始键态在哪条总线
# 用法：python capture_keys.py  然后挨个按 FL/FR/C/Z/M1-M4，每个按 2-3 次
import sys
import time

import hid

VID, PID = 0x37D7, 0x2501

devs = []
for d in hid.enumerate(VID, PID):
    devs.append(d)
    print(f'[{len(devs)-1}] if={d["interface_number"]} usage={d["usage_page"]:04X}/{d["usage"]:04X} {d["path"][:70].decode(errors="replace")}')

if not devs:
    print("手柄不在线")
    sys.exit(1)

opened = []
for i, d in enumerate(devs):
    try:
        h = hid.device()
        h.open_path(d["path"])
        opened.append((i, d, h))
        print(f"[{i}] opened OK")
    except Exception as e:
        print(f"[{i}] open FAILED: {e}")

last = {}
DURATION = 40
print(f"\n=== 现在开始按拓展键（FL/FR/C/Z/M1/M2/M3/M4），每个按 2-3 次，共 {DURATION} 秒 ===\n")
t0 = time.monotonic()
while time.monotonic() - t0 < DURATION:
    for i, d, h in opened:
        try:
            data = h.read(64, timeout_ms=4)
        except Exception:
            continue
        if not data:
            continue
        rep = bytes(data)
        prev = last.get(i)
        last[i] = rep
        if prev is None:
            print(f"[{i}] first: {rep.hex(' ')}")
            continue
        if rep == prev:
            continue
        diff = [f"{o:02d}:{p:02X}->{c:02X}" for o, (p, c) in enumerate(zip(prev, rep)) if p != c]
        print(f"[{i}] {rep[:16].hex(' ')}  changed: {' '.join(diff)}")

print("\n=== 抓包结束 ===")
