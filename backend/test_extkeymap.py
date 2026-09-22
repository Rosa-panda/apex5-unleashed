# ADR-030 extkeymap 离线测试：sanitize 白名单 / load+save 往返 / Runner 边沿注入。
# 不碰真机（send_kb 打桩）；跑法：python test_extkeymap.py
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

import extkeymap

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# ---- sanitize ----
cfg = extkeymap.sanitize({})
check("空配置→六键默认(透传,ADR-031)", set(cfg) == {"m1", "m2", "m3", "m4", "lm", "rm"}
      and cfg["m3"] == {"mode": "passthrough"}
      and cfg["rm"] == {"mode": "passthrough"})
bad = extkeymap.sanitize({"m1": {"mode": "haha"}, "m2": {"mode": "keyboard", "key": "F5"},
                          "m3": {"mode": "gamepad", "target": 999},
                          "m4": {"mode": "keyboard"}})
check("非法模式回退默认(透传)", bad["m1"] == {"mode": "passthrough"})
check("键名大写归一", bad["m2"] == {"mode": "keyboard", "key": "f5"})
check("非法目标回退LB", bad["m3"] == {"mode": "gamepad", "target": 10})
check("keyboard 缺键名回退 space", bad["m4"] == {"mode": "keyboard", "key": "space"})
check("has_keyboard", extkeymap.has_keyboard(bad) and not extkeymap.has_keyboard(cfg))

# ---- load/save 往返（临时目录，不碰真 APPDATA）----
tmp = tempfile.mkdtemp()
orig_path = extkeymap.cfg_path
extkeymap.cfg_path = lambda: os.path.join(tmp, "extkeymap.json")
try:
    check("无配置 load→默认(透传)", extkeymap.load()["m3"]["mode"] == "passthrough")
    want = extkeymap.sanitize({"m1": {"mode": "keyboard", "key": "f"}})
    extkeymap.save(want)
    got = extkeymap.load()
    check("save→load 往返", got["m1"] == {"mode": "keyboard", "key": "f"}
          and got["m2"] == {"mode": "passthrough"})
finally:
    extkeymap.cfg_path = orig_path

# ---- Runner 边沿（send_kb 打桩）----
sent = []
extkeymap.send_kb = lambda name, down: sent.append((name, down))
r = extkeymap.Runner()
r.cfg = extkeymap.sanitize({"m3": {"mode": "keyboard", "key": "f"},
                            "m4": {"mode": "gamepad", "target": 11}})
r.on_event({"kind": "extkey", "names": ["m3"]})
r.on_event({"kind": "extkey", "names": ["m3", "m4"]})     # gamepad 键不注入
r.on_event({"kind": "extkey", "names": ["m3", "m4"]})     # 无变化不重发
r.on_event({"kind": "extkey", "names": []})
check("边沿注入 down→up", sent == [("f", True), ("f", False)])
r.on_event({"kind": "device", "names": ["m3"]})
check("非 extkey 事件忽略", len(sent) == 2)
r.reload()
check("reload 清残留按下态", r._pressed == set())

print()
if failures:
    print(f"{len(failures)} 项失败: {failures}")
    sys.exit(1)
print("全部通过")
