# 探针3：背靠背连发 172（50ms 间隔，单次持续读循环收包），看固件读游标是否推进。
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import extkeys

pad = extkeys.Pad()
st = pad.read_status()
cfg = st["active"]
print(f"active cfg={cfg}")

frame = extkeys.build(172, bytes([cfg, 20]))
acks = []
end = time.time() + 3.0
next_send = 0.0
sent = 0
while time.time() < end and sent < 8:
    now = time.time()
    if now >= next_send:
        pad.dev.write(frame)
        sent += 1
        next_send = now + 0.05
        end = max(end, now + 1.0)
    r = bytes(pad.dev.read(64, timeout_ms=10))
    if len(r) > 7 and r[0] == 0x04 and r[1] == 0x5A and r[2] == 0xA5 and r[3] != 0xEF and r[3] == 172:
        acks.append((r[4], r[5]))
        print(f"ack: total={r[4]} idx={r[5]} data={r[7:27].hex()}")

print(f"\n发送 {sent} 次, 收到 {len(acks)} 包, idx 序列: {[a[1] for a in acks]}")
