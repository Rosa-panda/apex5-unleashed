# Mock 全链路冒烟（TEST-PLAN #1/#6/#8 部分）：WS 推送 + panic 账本清零 + 预设保存
import asyncio
import json
import urllib.request

import websockets

BASE = "http://127.0.0.1:18765"


def post(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body or {}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


async def main():
    async with websockets.connect("ws://127.0.0.1:18765/ws") as ws:
        snap = json.loads(await ws.recv())
        print("snapshot:", snap["device"], "| proxy:", snap["proxy"]["holder"])
        assert snap["device"]["online"] is True

        post("/api/trigger", {"side": "left", "mode": "lock",
                              "params": {"stroke": 120, "strength": 90}})
        got = []
        for _ in range(3):
            evt = json.loads(await asyncio.wait_for(ws.recv(), 3))
            got.append("{}:{}".format(evt["kind"], evt.get("result", "")))
        print("events:", " -> ".join(got))
        assert "command:ack" in " ".join(got)

        post("/api/panic")
        s = json.loads(urllib.request.urlopen(BASE + "/api/state").read())
        print("after panic: triggers =", s["state"]["triggers"], "| rumble =", s["state"]["rumble"])
        assert s["state"]["triggers"]["left"] is None and s["state"]["rumble"]["l"] == 0

        p = post("/api/presets", {"name": "冒烟测试预设", "note": "auto",
                                  "actions": [{"kind": "trigger", "side": "right",
                                               "mode": "race", "params": {"stroke": 90}}]})
        print("saved preset:", p["preset"]["id"])
        a = post("/api/presets/{}/apply".format(p["preset"]["id"]))
        print("apply:", a["result"])
        print("ALL SMOKE OK")


asyncio.run(main())
