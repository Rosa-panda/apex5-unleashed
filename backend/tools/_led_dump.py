# 只读诊断：抓取手柄当前灯表，逐帧×逐珠打印颜色，排查「右侧常亮」。
# 不写设备。跑法：python tools\_led_dump.py [后端地址]
import base64
import json
import sys
import urllib.request

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18765"
r = json.loads(urllib.request.urlopen(base + "/api/led/config", timeout=10).read())
bean, det = r.get("bean"), r.get("detect")
print("detect:", json.dumps(det, ensure_ascii=False))
print("bean:", json.dumps(bean, ensure_ascii=False))
if not r.get("frames_b64") or not bean:
    print("无帧表可解")
    sys.exit(0)
n = bean["rgb_num"]
raw = base64.b64decode(r["frames_b64"])
fsize = n * 3
nf = len(raw) // fsize
print(f"\n读回帧数={nf}  (帧大小={fsize}B)  loop_start={bean['loop_start']} "
      f"loop_end={bean['loop_end']}  loop_time={bean['loop_time']}  "
      f"亮度={bean['brightness']}  led_mode={bean['led_mode']}  grip_sync={bean.get('grip_sync')}")
print(f"读回总长={len(raw)}B，末尾零头 {len(raw) - nf * fsize}B\n")


def cell(c):
    return f"{c[0]:3d},{c[1]:3d},{c[2]:3d}"


for i in range(nf):
    fr = [tuple(raw[i * fsize + j * 3: i * fsize + j * 3 + 3]) for j in range(n)]
    lit = sum(1 for c in fr if max(c) > 0)
    desc = " ".join(cell(c) for c in fr)
    tag = "*" if bean["loop_start"] <= i <= bean["loop_end"] else " "
    print(f"[{i:3d}]{tag} 亮{lit:2d}  {desc}")
