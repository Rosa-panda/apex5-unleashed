# 全按键无输出·第二轮只读诊断（2026-09-22）。键表已排除（出厂全 255=透传）。
# 五路排查：XInput 槽位占用 / GeniTech 虚拟手柄驱动状态 / 当前档案 vs 出厂全字节 diff /
# proxy_hits 官方服务活动 / 工具后台状态。全程只读。
import ctypes
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

print("=== 1) XInput 槽位（虚拟手柄抢槽 = 全键无输出首嫌） ===")
xinput = ctypes.WinDLL("xinput1_4.dll")


class XINPUT_CAPABILITIES(ctypes.Structure):
    _fields_ = [("Type", ctypes.c_byte), ("SubType", ctypes.c_byte),
                ("Flags", ctypes.c_uint16),
                ("Vibration", ctypes.c_byte * 4),
                ("Gamepad", ctypes.c_byte * 12)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("Gamepad", ctypes.c_byte * 12)]


for slot in range(4):
    caps = XINPUT_CAPABILITIES()
    hr = xinput.XInputGetCapabilities(slot, 1, ctypes.byref(caps))
    st = XINPUT_STATE()
    pk = xinput.XInputGetState(slot, ctypes.byref(st))
    print(f"  slot{slot}: caps={hr} (0=有设备,1167=空) subtype={caps.SubType} "
          f"(1=游戏手柄,2=吉他…) packet={st.dwPacketNumber}")

print("=== 2) GeniTech 虚拟手柄驱动状态 ===")
try:
    import vibfix
    print(" ", vibfix.status())
except Exception as e:
    print("  查询失败:", e)

print("=== 3) 当前档案 vs 出厂 全字节 diff ===")
import extkeys
import profile as profile_mod

pad = extkeys.Pad()
st = pad.read_status()
cur = bytes(pad.read_config(st["active"]))
fac = bytes(profile_mod.factory_blob(st["active"]))
diffs = [i for i in range(min(len(cur), len(fac))) if cur[i] != fac[i]]
print(f"  槽{st['active']} 版本={cur[225] | (cur[226] << 8)} 差异字节数={len(diffs)}")
if diffs:
    # 聚成段
    segs, s = [], diffs[0]
    for a, b in zip(diffs, diffs[1:] + [None]):
        if b is not None and b == a + 1:
            continue
        segs.append((s, a))
        s = b
    for lo, hi in segs:
        print(f"  @{lo}-{hi}: 当前={cur[lo:hi+1].hex(' ')} 出厂={fac[lo:hi+1].hex(' ')}")

print("=== 4) proxy_hits.log 最近 8 条（官方服务接管活动） ===")
logp = os.path.join(os.environ["APPDATA"], "Apex5Unleashed", "proxy_hits.log")
if os.path.exists(logp):
    with open(logp, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    import time
    for ln in lines[-8:]:
        try:
            ts = float(ln.split(" ", 1)[0])
            age = time.time() - ts
            print(f"  {age/60:7.1f}分钟前 {ln.rstrip()[:130]}")
        except Exception:
            print(" ", ln.rstrip()[:140])
else:
    print("  无日志")

print("=== 5) 工具后台状态 ===")
import urllib.request
try:
    r = urllib.request.urlopen("http://127.0.0.1:18765/api/health", timeout=1)
    print("  18765 在线:", r.read(200))
except Exception as e:
    print("  18765 不在线:", e)
