# 探针：重新打开「私有原始数据」开关（cmd17），验证 0xEF 流恢复。
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import extkeys

pad = extkeys.Pad()

def read_flags():
    for body in pad.exchange(extkeys.build(16)):
        if body[2] == 16:
            return [body[5 + i] for i in range(5)]
    return None

print(f"开关（前）: {read_flags()}")
acks = pad.exchange(extkeys.build(17, bytes([255, 1, 255, 255, 255])))   # 仅开 私有原始数据
print(f"cmd17 ACK: {any(b[2] == 17 for b in acks)}")
print(f"开关（后）: {read_flags()}")

# 监听 6s 看 0xEF 是否回来
end = time.time() + 6
n = 0
last = None
while time.time() < end:
    r = bytes(pad.dev.read(64, timeout_ms=50))
    if len(r) > 14 and r[0] == 0x04 and r[3] == 0xEF:
        n += 1
        cur = r[11] | (r[12] << 8) | (r[13] << 16) | (r[14] << 24)
        if cur != last:
            last = cur
            print(f"  位图: {cur:08x}")
print(f"6s 收到 0xEF 帧: {n}")
