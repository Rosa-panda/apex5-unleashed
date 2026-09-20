# 游戏档案 + 前台自动切换状态机单测（不依赖真实前台：注入假 exe）
# 2026-09-20 语义更新（用户定则）：内置档案默认【不走】扳机预设——
# 预设绑定只能是用户显式行为；官方 vib 震动联动不受影响。
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

# 2. 新策略：内置档案默认不带 preset_id → 进老头环不套预设，明确提示标准模式
assert not g.get("preset_id"), f"内置档案不应出厂绑预设: {g.get('preset_id')}"
gameprofiles.foreground_exe = lambda: "eldenring.exe"
games.maybe_autoswitch(eng)
time.sleep(0.2)
t = eng.state["triggers"]["left"]
assert t is None, f"默认不应套预设，实际 {t}"
print("default no-preset policy OK（老头环标准模式）")

# 3. 显式绑定 → 自动套用（用户在 UI 里给游戏绑预设的唯一入口）
saved = games.save({"name": "测试绑定游戏", "exe": ["presetgame.exe"],
                    "preset_id": "fps-sniper", "note": "test-only"})
try:
    gp = games.match("presetgame.exe")
    assert gp and gp.get("preset_id") == "fps-sniper", gp
    gameprofiles.foreground_exe = lambda: "presetgame.exe"
    games.maybe_autoswitch(eng)
    time.sleep(0.2)
    t = eng.state["triggers"]["left"]
    assert t and t["source"].startswith("preset:"), t
    assert t["mode"] == "sniper", t
    print("explicit link autoswitch applies preset OK:", t["mode"], "<-", t["source"])

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
