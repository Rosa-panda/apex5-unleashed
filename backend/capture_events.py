# 拓展键逐事件抓取：带时间戳记录每个按下/松开沿（ADR-016 受控归因取证）
# 用法：python capture_events.py [秒数]  输出 %TEMP%\keyevents.log
# 与常驻软件并存：HID 多句柄广播读取，互不干扰。
import sys
import time
from datetime import datetime

import hid

VID, PID = 0x37D7, 0x2501
DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
LOG = __import__("os").path.join(__import__("os").environ.get("TEMP", "."), "keyevents.log")


def find(usage):
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == 0x0001 and d.get("usage") == usage:
            return d["path"]
    return None


def watch(path, tag, stop_at, f):
    dev = hid.device()
    try:
        dev.open_path(path)
    except Exception as e:
        f.write(f"[{tag}] open fail: {e}\n")
        return
    bits = {}
    while time.time() < stop_at:
        try:
            data = dev.read(64, timeout_ms=20)
        except Exception:
            break
        if not data or len(data) < 11:
            continue
        rep = bytes(data)
        for off in range(10, min(len(rep), 14)):
            for b in range(8):
                key = (off, b)
                on = bool(rep[off] & (1 << b))
                if bits.get(key, False) != on:
                    bits[key] = on
                    t = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    f.write(f"{t} {tag} b{off}.{b} {'DOWN' if on else 'UP  '}\n")
                    f.flush()
    dev.close()


def main():
    stop_at = time.time() + DURATION
    with open(LOG, "w", encoding="utf-8") as f:
        f.write(f"capture start {datetime.now()} duration={DURATION}s\n")
        targets = []
        p = find(0x0005)   # gamepad
        if p:
            targets.append((p, "pad "))
        p = find(0x0006)   # keyboard
        if p:
            targets.append((p, "kbd "))
        threads = []
        for path, tag in targets:
            import threading
            th = threading.Thread(target=watch, args=(path, tag, stop_at, f), daemon=True)
            th.start()
            threads.append(th)
        f.write(f"watching {len(targets)} interfaces\n")
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
        f.write("capture end\n")
    print("saved:", LOG)


if __name__ == "__main__":
    main()
