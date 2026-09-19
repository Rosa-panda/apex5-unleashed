# 键盘接口原始监听（键盘编码实验观测端）：打印所有非空键盘报告
# 用法：python kb_capture.py [监听秒数，默认 600]
import sys
import time

import keymonitor

SECS = int(sys.argv[1]) if sys.argv[1:] else 600
path = keymonitor.find_keyboard_path()
if not path:
    print("未找到键盘接口")
    sys.exit(1)

import hid
print(f"监听键盘接口 {SECS}s，等待按键…")
end = time.time() + SECS
n = 0
dev = None
while time.time() < end:
    try:
        if dev is None:
            p = keymonitor.find_keyboard_path()
            if not p:
                time.sleep(1.0)
                continue
            dev = hid.device()
            dev.open_path(p)
        r = bytes(dev.read(64, timeout_ms=100))
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] 接口异常，1s 后重开: {e}", flush=True)
        dev = None
        time.sleep(1.0)
        continue
    if len(r) >= 8 and any(r[1:9]):
        n += 1
        keys = keymonitor.KEYCODES.get
        named = [keys(b, f"{b:#04x}") for b in r[3:9] if b] or ["-"]
        print(f"[{time.strftime('%H:%M:%S')}] mods={r[1]:#04x} keys={' '.join(named)}  raw={r.hex(' ')}", flush=True)
print(f"结束，共 {n} 条报告")
