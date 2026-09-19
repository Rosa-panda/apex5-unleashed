# 代理权恢复状态机单测（不碰总线）：external → 空闲超时自动恢复 → reassert 账本重放
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import engine as m

eng = m.Engine(force_mock=True)
eng.attach(m.transport.MockPad())
time.sleep(0.3)

# 1. 先放一个效果进账本（reassert 要重放它）
eng.set_trigger("right", "recoil", {"stroke": 200, "strength": 220}, source="test")
assert eng.state["triggers"]["right"]["mode"] == "recoil"

# 2. 模拟外部命令命中（绕过总线，直接打状态机）
eng._pending.clear()
eng._external_hit(0x51)
assert eng.proxy["holder"] == "external", "铁证应置 external"
print("hit -> external OK")

# 3. 15s 未到：不恢复
eng.maybe_release_proxy()
assert eng.proxy["holder"] == "external", "15s 内不应恢复"
print("within timeout: stay external OK")

# 4. 时间快进：应自动恢复并重放账本（RT recoil 应再次下发）
eng._last_external = time.monotonic() - m.PROXY_RELEASE_TIMEOUT - 1
events_before = len(eng.events)
eng.maybe_release_proxy()
assert eng.proxy["holder"] == "self", "超时后应恢复 self"
tail = [e for e in list(eng.events)[events_before:] if e["kind"] == "command" and e.get("source") == "reclaim"]
assert any("51" in (e.get("hex") or "") for e in tail), "reassert 应重发 cmd81 (recoil)"
print("timeout -> reclaim + reassert OK, replayed cmds:", len(tail))

# 5. 手动夺回通道
eng._external_hit(0x12)
assert eng.proxy["holder"] == "external"
eng.reclaim()
assert eng.proxy["holder"] == "self"
print("manual reclaim OK")
print("ALL RECLAIM TESTS PASS")
eng.stop()
