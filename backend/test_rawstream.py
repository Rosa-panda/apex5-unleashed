# -*- coding: utf-8 -*-
"""rawstream.RawStreamHub 单测（ADR-028 修订 2）：需求登记表/心跳超时/去重下发。"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))
from rawstream import RawStreamHub  # noqa: E402


class FakeEngine:
    online = True
    raw_motion = False

    def __init__(self):
        self.send_count = 0
        self.last_source = None

    def set_raw_motion(self, on, source="ui"):
        self.send_count += 1
        self.raw_motion = bool(on)
        self.last_source = source


def make(timeout=30.0):
    e = FakeEngine()
    return e, RawStreamHub(e, timeout=timeout, watchdog_interval=0.05)


def test_default_off():
    e, hub = make()
    assert hub.eval("boot") is False and e.raw_motion is False


def test_demand_opens_closes():
    e, hub = make()
    hub.demands["macro"] = True
    assert hub.eval() is True and e.raw_motion is True
    hub.demands["macro"] = False
    assert hub.eval() is False and e.raw_motion is False


def test_heartbeat_timeout():
    e, hub = make(timeout=0.1)
    hub.heartbeat(True)
    assert hub.eval() is True and e.raw_motion is True
    time.sleep(0.15)
    assert hub.eval("watchdog") is False and e.raw_motion is False


def test_heartbeat_off_is_immediate():
    e, hub = make()
    hub.heartbeat(True)
    hub.eval()
    hub.heartbeat(False)
    assert hub.eval() is False and e.raw_motion is False


def test_no_duplicate_send():
    e, hub = make()
    hub.demands["master"] = True
    assert hub.eval() is True
    assert e.send_count == 1
    hub.eval("noop")              # 期望态==实际态：不应重复下发 cmd17
    assert e.send_count == 1


def test_watchdog_reclaims():
    e, hub = make()
    hub.demands["padlive"] = True  # 无效位不参与决策，验证 watchdog 不误开
    hub.start_watchdog()
    e.raw_motion = True            # 模拟宏/档案写后强开
    deadline = time.monotonic() + 2
    while e.raw_motion and time.monotonic() < deadline:
        time.sleep(0.02)
    assert e.raw_motion is False, "watchdog 30s 内（此处 0.05s tick）应收回无人消费的流"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)}/{len(fns)} 绿")
