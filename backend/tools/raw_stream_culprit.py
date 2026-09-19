# 探针：定位冲掉「私有原始数据」开关的操作——逐一做 162 应用 / 166 保存，每步后查开关。
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import extkeys

pad = extkeys.Pad()

def flags():
    for body in pad.exchange(extkeys.build(16)):
        if body[2] == 16:
            return [body[5 + i] for i in range(5)]
    return None

st = pad.read_status()
cfg = st["active"]
ver = st["versions"][cfg]
print(f"cfg={cfg} ver={ver}")
print(f"初始开关: {flags()}")

pad.apply(cfg)
print(f"162 应用后: {flags()}")

acks = pad.exchange(extkeys.build(extkeys.CMD_SAVE, struct.pack("<H", ver)), wait=1.5)
print(f"166 保存 ACK: {any(b[2] == extkeys.CMD_SAVE for b in acks)}")
print(f"166 保存后: {flags()}")
