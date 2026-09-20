# 探针公共件（企划书 §一 探针周）：全只读/可恢复，产出人可读报告。
# ⚠ 运行任何探针前先退出本工具（托盘角标→退出）：探针用自己的 HID 句柄发命令，
#   工具在跑会把这些 ACK 当外部命令 → 误判「被接管」并触发收回（代理权自激）。
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

import extkeys  # noqa: E402  （复用 Pad：vendor 接口第二句柄 + 校验和帧）


def open_pad():
    return extkeys.Pad()


def exchange_try(pad, cmd, payload=b"", wait=0.8):
    """同一命令先试校验和帧、无 ACK 再试无校验帧（k5 各命令族校验行为不统一，
    探针期两把都摸，记录哪种有效——结论回填企划书/RESEARCH）。返回 (bodies, used_crc)。"""
    bodies = pad.exchange(extkeys.build(cmd, payload), wait=wait)
    if bodies:
        return bodies, True
    import protocol
    bodies = pad.exchange(protocol.build(cmd, payload), wait=wait)
    return bodies, False


def hd(b, start=0, end=None):
    """人可读 hex 行。"""
    end = end or len(b)
    return " ".join(f"{x:02X}" for x in b[start:end])


def bits(v, n=8):
    return " ".join(f"b{i}={bool(v >> i & 1):d}" for i in range(n))


def report(title):
    print("=" * 62)
    print(title)
    print("=" * 62)


def wait_user(prompt):
    try:
        input(prompt)
    except EOFError:
        time.sleep(3)
