# 帧构型实验：cmd 161 四种变体，观察哪种有应答（只读探测）
import time

import hid

VID, PID = 0x37D7, 0x2501


def open_vendor():
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == 0xFFA0:
            dev = hid.device()
            dev.open_path(d["path"])
            return dev
    raise RuntimeError("vendor 接口未找到")


def checksum(buf, start, end):
    return sum(buf[start:end]) & 0xFF


def frame(cmd, payload=b"", len_mode="plus2", crc=True):
    buf = bytearray(32)
    buf[0], buf[1], buf[2], buf[3] = 0x03, 0x5A, 0xA5, cmd
    buf[4] = len(payload) + (2 if len_mode == "plus2" else 0)
    buf[5:5 + len(payload)] = payload
    if crc:
        buf[3 + buf[4]] = checksum(buf, 3, 3 + buf[4])
    return bytes(buf)


dev = open_vendor()

def drain(sec):
    end = time.time() + sec
    got = []
    while time.time() < end:
        for r in dev.read(64, timeout_ms=30):
            r = bytes(r)
            if len(r) > 7 and r[1:3] == b"\x5A\xA5":
                got.append(r)
    return got

print("基线静默期采样 1s ...", drain(1.0) and "（有帧）" or "（静默）")

variants = [
    ("len=+2 crc", frame(161, b"", "plus2", True)),
    ("len=+0 crc", frame(161, b"", "plus0", True)),
    ("len=+2 nocrc", frame(161, b"", "plus2", False)),
    ("len=+0 nocrc", frame(161, b"", "plus0", False)),
]
for name, f in variants:
    dev.write(f)
    replies = drain(0.8)
    cmds = [f"{r[3]:02X}" for r in replies]
    print(f"{name}: {f.hex(' ')}  -> {len(replies)} 帧 cmd={cmds[:6]}")
