# 游戏档案 + 前台自动切换状态机单测（不依赖真实前台：注入假 exe）
# 2026-11：游戏不再绑扳机预设，适配 = 震动联动参数 / 官方 Mod；支持导入自定义配置。
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
# 不吃用户真实 settings.json：本测固定语义（直接赋属性，不走 setter → 不落盘）
games.autoswitch = True
games.universal_vib = False
games._was_online = True                    # 排除 attach 沿重放干扰

# 前台探测注入点（收尾还原真实 Win32 实现）
_orig_fg = gameprofiles.foreground_exe

# 1. 内置档案加载 + 匹配
all_ = games.all()
assert len(all_) >= 7, f"内置档案应>=7，实际 {len(all_)}"
g = games.match("eldenring.exe")
assert g and g["name"].startswith("艾尔登法环"), g
print("builtin load + exe match OK")

# 2. 游戏不再绑预设（2026-11）：进老头环不动扳机模式
gameprofiles.foreground_exe = lambda: "eldenring.exe"
games.maybe_autoswitch(eng)
time.sleep(0.2)
t = eng.state["triggers"]["left"]
assert t is None, f"不应套扳机预设，实际 {t}"
print("no-preset policy OK")

# 3. 导入自定义配置 → 进游戏自动套用其震动参数
saved = games.import_config({"name": "测试自定义游戏", "exe": ["customgame.exe"], "note": "test-only",
                             "vib": {"filter": 1, "scale": 10, "stroke": 0, "press": 1,
                                     "strength": 90, "freq": 12}})[0]
try:
    gp = games.match("customgame.exe")
    assert gp and gp["vib_origin"] == "custom" and gp["origin"] == "custom", gp
    gameprofiles.foreground_exe = lambda: "customgame.exe"
    games.maybe_autoswitch(eng)
    time.sleep(0.2)
    gb = eng.state["gripBind"]["left"]
    assert gb and gb["strength"] == 90 and gb["source"] == "game:测试自定义游戏", gb
    print("custom config autoswitch OK:", gb)

    # 4. 迟滞：前台不变不重复应用
    before = len(eng.events)
    games.maybe_autoswitch(eng)
    after = len(eng.events)
    assert after - before == 0, "前台未变化不应产生事件"
    print("hysteresis OK")
finally:
    games.delete(saved["id"])

# 5. 离开游戏 → 账本非空 → 解绑 + 扳机回 Normal（autoswitch:leave）
gameprofiles.foreground_exe = lambda: "notepad.exe"
games.maybe_autoswitch(eng)
t2 = eng.state["triggers"]["left"]
assert t2 and t2["mode"] == "normal" and "unbind" in t2["source"], t2
assert games.foreground == "notepad.exe"
print("leave-game unbind OK")

# 5.5 桌面闲逛完全静默（离开适配后，非游戏前台间切换不发 autoswitch 事件）
before = len(eng.events)
for exe in ("explorer.exe", "chrome.exe", "explorer.exe"):
    gameprofiles.foreground_exe = lambda exe=exe: exe
    games.maybe_autoswitch(eng)
evts = [e for e in list(eng.events)[before:] if e["kind"] == "autoswitch"]
assert not evts, f"桌面闲逛不应发 autoswitch 事件: {evts}"
print("desktop wandering silent OK")

# 6. autoswitch 关闭时不动作
games.autoswitch = False
gameprofiles.foreground_exe = lambda: "gta5.exe"
before = len(eng.events)
games.maybe_autoswitch(eng)
evts = list(eng.events)[before:]
assert not any(e["kind"] == "autoswitch" for e in evts), "关闭后不应自动应用"
print("autoswitch off OK")

gameprofiles.foreground_exe = _orig_fg
print("ALL GAME PROFILE TESTS PASS")
eng.stop()
