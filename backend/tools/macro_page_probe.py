# 探针4：只读验证 openflydigi 结论——k5 的宏页在 163 profile blob 偏移 230，间隔字节在 820。
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import extkeys

pad = extkeys.Pad()
st = pad.read_status()
cfg = st["active"]
blob = pad.read_config(cfg)
pad.apply(cfg)
print(f"active cfg={cfg} blob={len(blob)}B")
print(f"proto_version = {blob[0] | (blob[1] << 8)} (hi.lo = {blob[1]}.{blob[0]})")
print(f"package count @2 = {blob[2]}")
print(f"data version @225 = {blob[225] | (blob[226] << 8)}")

page = blob[230:768]
print(f"\n宏页 @230 前 24B: {page[:24].hex()}")
count = page[0]
print(f"count 字节 = {count:#x} ({'有效' if 1 <= count <= 5 else '无效→无宏'})")
if 1 <= count <= 5:
    offs = list(page[1:1 + count])
    print(f"offsets = {offs}")
    for s in range(count):
        start = 6 + offs[s] * 4
        end = 6 + offs[s + 1] * 4 if s + 1 < count else len(page)
        body = page[start:end]
        steps_stored = body[1] | (body[2] << 8)
        print(f"  槽{s}: 触发键={body[0]} 步数={steps_stored} 类型={body[3]} "
              f"前几步={body[4:20].hex()}")

print(f"\n间隔字节 @820: {list(blob[820:825])} (0xFF=未设, 值×10ms; 出厂约 3=30ms)")
print(f"键表 M1-M6 target: {[blob[13 + k * 3] for _, k in extkeys.EXT_KEYS]}")
