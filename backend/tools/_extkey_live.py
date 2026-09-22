# 拓展键断点定位实采（2026-09-22）：0xEF 物理位图 × gamepad HID 输出双通道。
# 背景：cmd29 重启后基础键恢复、拓展键「没法用」。cmd17 私有流开关是 RAM 态重启会丢，
# 先补开；然后 60s 采集：位图变=固件收到了按压；HID byte[10] 变=映射输出到标准报告。
# 结束后关流（恢复可休眠卫生态）。
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import extkeys
import hid

NAMES = {0: "up", 1: "right", 2: "down", 3: "left", 4: "a", 5: "b", 6: "select", 7: "x",
         8: "y", 9: "start", 10: "lb", 11: "rb", 12: "lt", 13: "rt", 14: "thl", 15: "thr",
         16: "c", 17: "z", 18: "M1", 19: "M2", 20: "M3", 21: "M4", 22: "LM", 23: "RM",
         24: "menu", 25: "turbo", 27: "home", 28: "back"}

pad = extkeys.Pad()
ok = extkeys.enable_raw_stream(pad)
print(f"cmd17 开流: {ok}")

# gamepad HID 句柄
gp = hid.device()
for d in hid.enumerate(0x37D7, 0x2501):
    if d.get("usage_page") == 1 and d.get("usage") == 5:
        gp.open_path(d["path"])
        break

pad.dev.set_nonblocking(True)
gp.set_nonblocking(True)
bits_prev = None
gp_prev = None
n_ef = 0
t0 = time.time()
DUR = 180
print(f"开始 {DUR}s 采集——请依次按 M1 M2 M3 M4 LM RM，最后按一下 A 作对照")
try:
    while time.time() - t0 < DUR:
        r = bytes(pad.dev.read(64))
        if len(r) > 15 and r[1:4] == b"\x5a\xa5\xef":
            n_ef += 1
            bits = int.from_bytes(r[12:16], "little")   # body=r[1:] → body[11:15]
            if bits != bits_prev:
                el = time.time() - t0
                if bits_prev is not None:
                    diff = bits ^ bits_prev
                    downs = [NAMES.get(i, str(i)) for i in range(32) if diff >> i & 1 and bits >> i & 1]
                    ups = [NAMES.get(i, str(i)) for i in range(32) if diff >> i & 1 and not bits >> i & 1]
                    print(f"  [{el:5.1f}s] 位图: {'按下 ' + '+'.join(downs) if downs else ''}"
                          f"{'松开 ' + '+'.join(ups) if ups else ''}")
                bits_prev = bits
        g = bytes(gp.read(64))
        if len(g) >= 11:
            sig = (g[10],)
            if sig != gp_prev:
                el = time.time() - t0
                if gp_prev is not None:
                    b = g[10]
                    outs = [nm for nm, m in [("LB", 0x10), ("RB", 0x20), ("0x40", 0x40), ("0x80", 0x80),
                                             ("select", 0x01), ("start", 0x02)] if b & m]
                    print(f"  [{el:5.1f}s] HID byte10={b:02x} → {'+'.join(outs) or '无'}")
                gp_prev = sig
finally:
    pad.dev.set_nonblocking(False)
    pad.exchange(extkeys.build(17, bytes([255, 0, 255, 255, 255])), wait=0.3)
    print(f"结束：0xEF 收 {n_ef} 帧，流已关")
