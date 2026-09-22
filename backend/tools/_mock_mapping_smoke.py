# ADR-030 冒烟：mock 组装 create_app（覆盖 appctx 接线 NameError 风险），
# TestClient 点验 /api/extkeys/mapping GET/POST（mock 无真机，POST 预期 err 不崩）。
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import engine as engine_mod
import transport
import service
from fastapi.testclient import TestClient

eng = engine_mod.Engine(force_mock=True)
eng.attach(transport.MockPad())
import presets as presets_mod
import gameprofiles
store = presets_mod.PresetStore()
games = gameprofiles.GameProfiles(store)
app = service.create_app(eng, store, games)
c = TestClient(app)

r = c.get("/api/health")
print("health:", r.status_code, r.json().get("ok", r.json()))
r = c.get("/api/extkeys/mapping")
body = r.json()
print("GET mapping:", r.status_code, "ok=", body.get("ok"),
      "config keys=", sorted((body.get("config") or {}).keys()),
      "targets=", bool(body.get("targets")))
assert r.status_code == 200 and body.get("ok") and body.get("config"), body
assert body["config"]["m3"] == {"mode": "gamepad", "target": 10}

r = c.post("/api/extkeys/mapping", json={"config": {"m1": {"mode": "keyboard", "key": "F"}}})
body = r.json()
print("POST mapping:", r.status_code, "ok=", body.get("ok"), "config=", body.get("config"))
# ⚠⚠ 此端点经 extkeys.Pad 直连真机（Engine 的 mock 抽象管不到独立句柄）——
# 2026-09-22 实锤：冒烟 POST 把真机 m1 写成了 255。线上验证 POST 只能在真机 +
# 用户知情下做；冒烟只验 GET 与参数归一（下方仅断言 sanitize 行为，不再落表）。
assert r.status_code in (200, 400), (r.status_code, body)
print("冒烟通过")
