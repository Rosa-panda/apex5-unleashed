# 真机校准（ADR-017 风险项）：cmd 0x52 SyncWithGrip 参数映射验证
# 走运行中后端的 HTTP API（HID 单实例，不直开设备）：
#   套用官方「战地6」档案（vib 绑定双侧）→ 震动脉冲 8 秒 → 恢复
import json
import time
import urllib.request

BASE = "http://127.0.0.1:18765"


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read() or b"{}")


def main():
    health = call("GET", "/api/health")
    assert health.get("online") is True, f"设备不在线: {health}"

    games = call("GET", "/api/games")
    pool = {g["name"]: g for grp in ("user", "builtin") for g in games.get(grp, [])}
    target = next((pool[n] for n in pool if "战地" in n and pool[n].get("vib")), None)
    assert target, "没找到带 vib 的战地档案"
    print(f">> 套用官方档案「{target['name']}」 vib={target['vib']}")
    r = call("POST", f"/api/games/{target['id']}/apply")
    print("   apply:", r)
    time.sleep(0.5)

    print(">> 8 秒震动脉冲 —— 请按住 LT/RT 感受扳机是否随节奏反馈…")
    for i in range(8):
        call("POST", "/api/rumble", {"l": 200, "r": 200})
        time.sleep(0.4)
        call("POST", "/api/rumble", {"l": 0, "r": 0})
        time.sleep(0.6)
        print(f"   脉冲 {i + 1}/8")

    print(">> 恢复：解绑震动联动")
    call("POST", "/api/panic")          # 全清回 Normal
    print("DONE — 请反馈：①震动期间扳机有反馈吗 ②强度/手感如何 ③停震后是否静止")


if __name__ == "__main__":
    main()
