# 裸抓：发 cmd161 后 2 秒内所有 HID 输入报告原样 dump（不过滤 report id / 帧头）
import sys
import time

import hid

VID, PID = 0x37D7, 0x2501


def checksum(buf, start, end):
    return sum(buf[start:end]) & 0xFF


def build(cmd, payload=b""):
    buf = bytearray(32)
    buf[0], buf[1], buf[2], buf[3] = 0x03, 0x5A, 0xA5, cmd
    buf[4] = len(payload) + 2
    buf[5:5 + len(payload)] = payload
    buf[3 + buf[4]] = checksum(buf, 3, 3 + buf[4])
    return bytes(buf)


dev = hid.device()
for d in hid.enumerate(VID, PID):
    if d.get("usage_page") == 0xFFA0:
        dev.open_path(d["path"])
        break
else:
    print("vendor 接口未找到")
    sys.exit(1)
dev.set_nonblocking(False)

frame = build(161)
print("TX:", frame.hex(" "))
dev.write(frame)
end = time.time() + 2.0
n = 0
while time.time() < end:
    r = dev.read(64, timeout_ms=50)
    if r:
        n += 1
        print(f"RX[{n}] len={len(r)}:", bytes(r).hex(" "))
        end = max(end, time.time() + 0.3)
if n == 0:
    print("2 秒内零输入报告")
dev.close()
