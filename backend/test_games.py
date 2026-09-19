# 游戏档案 + 前台自动切换状态机单测（不依赖真实前台：注入假 exe）
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import engine as m
import gameprofiles
import presets as presets_mod
import transport

eng = m.Engine(force_mock=True)
eng.attach(transport.MockPad())
time.sleep(0.2)

store = presets_mod.PresetStore()
games = gameprofiles.GameProfiles(store)

# 1. 内置档案加载 + 匹配
all_ = games.all()
assert len(all_) >= 7, f"内置档案应>=7，实际 {len(all_)}"
g = games.match("eldenring.exe")
assert g and g["name"].startswith("艾尔登法环"), g
print("builtin load + exe match OK")

# 2. 自动切换：前台变 eldenring.exe → 应自动应用 fps-sniper
games.maybe_autoswitch.__func__  # noqa
# 注入假前台（绕过 Win32）
games.foreground = "dummy.exe"
fake_fg = {"eldenring.exe": "eldenring.exe"}
orig = gameprofiles.foreground_exe
gameprofiles.foreground_exe = lambda: "eldenring.exe"
games.maybe_autoswitch(eng)
time.sleep(0.2)
t = eng.state["triggers"]["left"]
assert t and t["source"].startswith("preset:"), t
assert "狙击" in t["source"] or "FPS" in t["source"] or "sniper" in t["source"].lower(), t
print("autoswitch applies preset OK:", t["mode"], "<-", t["source"])

# 3. 迟滞：前台不变不重复应用
before = len(eng.events)
games.maybe_autoswitch(eng)
after = len(eng.events)
assert after - before == 0, "前台未变化不应产生事件"
print("hysteresis OK")

# 4. 无匹配档案：ADR-017 后离开游戏 → 解绑震动联动 + 扳机回 Normal（非 preset 账本）
gameprofiles.foreground_exe = lambda: "notepad.exe"
games.maybe_autoswitch(eng)
t2 = eng.state["triggers"]["left"]
assert t2 and t2["mode"] == "normal" and "unbind" in t2["source"], t2
assert games.foreground == "notepad.exe"
print("no-match unbinds vib OK")

# 5. autoswitch 关闭时不动作
games.autoswitch = False
gameprofiles.foreground_exe = lambda: "gta5.exe"
before = len(eng.events)
games.maybe_autoswitch(eng)
evts = list(eng.events)[before:]
assert not any(e["kind"] == "autoswitch" for e in evts), "关闭后不应自动应用"
print("autoswitch off OK")

gameprofiles.foreground_exe = orig
print("ALL GAME PROFILE TESTS PASS")
eng.stop()
