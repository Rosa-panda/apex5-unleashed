# 回归：同 cmd 连发 + ACK 迟到批量到达时，FIFO pending 必须逐个匹配，不得误判外部代理。
# 背景：真机上 panic/reassert 的双侧 cmd51 连发，ACK 慢于写入 → 旧 dict pending 被 R 覆盖，
# ACK L 消费 R 的记录 → ACK R 成孤儿 → 被判 external → 15s 后 reclaim 又连发 → 无限自激「被代理」。
import os
import sys
import time
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import engine as m
import protocol


class LazyPad:
    """真机行为模拟：ACK 延迟 30ms 到达（超过 worker 单轮 read 的 10ms 窗口 → 写入会批量排队）。"""
    kind = "mock"

    def __init__(self):
        self._inbox = deque()

    def write(self, buf):
        cmd = buf[3]
        self._inbox.append((time.monotonic() + 0.030, protocol.mock_ack_frame(cmd)))
        return len(buf)

    def read(self, timeout_ms):
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            if self._inbox and self._inbox[0][0] <= time.monotonic():
                return self._inbox.popleft()[1]
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.001)

    def close(self):
        pass


eng = m.Engine(force_mock=True)
eng.attach(LazyPad())
eng.panic(source="startup")               # 双侧 cmd51 连发
eng.set_trigger("left", "sniper", {"stroke": 5}, source="t")
eng.clear_trigger("left", source="t")
time.sleep(0.5)

assert eng.proxy["holder"] == "self", f"自己的命令不应触发外部判定: {eng.proxy}"
assert not eng._ext_cmds, f"不应有外部命令计数: {eng._ext_cmds}"
sent = [e for e in eng.events if e["kind"] == "command"]
assert not any(c["result"] == "timeout" for c in sent), sent

# 构造真孤儿：pending 为空时收到协议 ACK 帧 → 应判 external（这才是真外部活动）
eng._classify(protocol.mock_ack_frame(0x51))
assert eng.proxy["holder"] == "external", "真外部命令应被识别"

eng.stop()
print("PENDING FIFO + EXTERNAL DETECTION OK")
