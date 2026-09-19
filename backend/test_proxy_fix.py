# 代理权误判修复（孤儿 ACK 宽限窗）自检：直接驱动 Engine._classify，不需要真设备。
# 跑法：python test_proxy_fix.py
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import engine as E

ok = 0


def check(name, cond):
    global ok
    assert cond, f"✗ {name}"
    ok += 1
    print(f"✓ {name}")


def ack_frame(cmd, b3=0, b4=0):
    """一条引擎句柄会收到的协议帧（带 report id 头，_classify 自己剥）。"""
    return bytes([0x04, 0x5A, 0xA5, cmd, b3, b4, 0, 0, 0, 0])


eng = E.Engine(force_mock=True)
holder = lambda e=None: (e or eng).proxy["holder"]

# ---- 1. 引擎自己的多包读（42 包读的第 2..N 包）不算外部 ----
eng._last_tx[163] = time.monotonic()
for _ in range(41):
    eng._classify(ack_frame(163, 42, 1))
check("引擎多包读 41 个多余回复不翻代理", holder() == "self")
check("孤儿回复计数已记录", eng._orphan_replies.get(163) == 41)

# ---- 2. 第二句柄（extkeys.Pad 独占会话）的回复不算外部 ----
eng2 = E.Engine(force_mock=True)
import extkeys
extkeys._TX_SEEN.clear()
extkeys._TX_SEEN[161] = time.monotonic() - 1.0   # Pad 会话 1s 前发过 161
eng2._classify(ack_frame(161))
check("第二句柄 1s 前发的 161 回复不翻代理", holder(eng2) == "self")
eng2._classify(ack_frame(162))
check("第二句柄从没发过的 162 仍判外部（真·铁证保留）", holder(eng2) == "external")

# ---- 2b. _stream 流式直写（震动/正弦测试）也登记宽限 ----
eng2b = E.Engine(force_mock=True)
eng2b._note_tx(0x12)                       # _stream 每次直写都会调 _note_tx
eng2b._classify(ack_frame(0x12))
check("震动流直写后的 cmd18 ACK 不翻代理", holder(eng2b) == "self")

# ---- 3. 宽限窗过期后，同命令号的孤儿回复恢复判定为外部 ----
eng3 = E.Engine(force_mock=True)
eng3._last_tx[163] = time.monotonic() - (E.REPLY_GRACE + 1)
eng3._classify(ack_frame(163))
check("宽限窗（5s）外的迟到回复仍判外部", holder(eng3) == "external")

# ---- 4. 普通写命令的孤儿 ACK（非宽限场景）行为不变 ----
eng4 = E.Engine(force_mock=True)
eng4._classify(ack_frame(0x51))
check("从没发过的 0x51 回复判外部（原逻辑不回归）", holder(eng4) == "external")

# ---- 5. detach 复位代理权（离线不再卡「被接管」） ----
eng5 = E.Engine(force_mock=True)
eng5.dev_kind = "real"
eng5.online = True
eng5.proxy = {"holder": "external", "detail": "未知进程", "since": "x"}
eng5.detach("测试")
check("detach 后代理权复位为 self", holder(eng5) == "self")

# ---- 6. attach 复位代理权 ----
class FakeDev:
    kind = "mock"
    def write(self, f): pass
    def read(self, t): return []
    def close(self): pass

eng6 = E.Engine(force_mock=True)
eng6.proxy = {"holder": "external", "detail": "未知进程", "since": "x"}
eng6.attach(FakeDev())
check("attach 后代理权复位为 self", holder(eng6) == "self")
eng6.detach("收尾")   # 停掉 worker 线程

print(f"\n全部 {ok} 项通过")
