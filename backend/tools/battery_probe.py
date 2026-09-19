# 只读探针：cmd1 心跳回复里抓电量（openflydigi：raw[12] 低半字节=电量0..5，高半字节1=充电中）。
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import extkeys

pad = extkeys.Pad()

def show(tag, replies):
    for r in replies:
        hexs = r.hex(" ")
        note = ""
        if len(r) > 12 and r[0] == 0x04 and r[1:3] == b"\x5a\xa5" and r[3] == 1:
            b = r[12]
            note = f"  ← cmd1: 设备类型={r[6]} 连接={r[7]} 电量字节=0x{b:02x} " \
                   f"→ 电量={b & 0xF}/5 {'充电中' if (b >> 4) == 1 else ''}"
        print(f"[{tag}] {hexs}{note}")

show("心跳", pad.exchange(extkeys.build(1), wait=0.8))
show("心跳+0", pad.exchange(extkeys.build(1, b"\x00"), wait=0.8))
