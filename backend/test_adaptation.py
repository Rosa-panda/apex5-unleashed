# ADR-017 自检：官方适配导入 + vib 震动联动应用 + 通用回落 + 自定义 exe（全 Mock，不碰真机）
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import engine as m
import gameprofiles
import officialimport
import presets as presets_mod
import transport

# 隔离用户数据目录（不污染真实 %APPDATA%）
_tmp = tempfile.mkdtemp(prefix="a5test-")
os.environ["APPDATA"] = _tmp

eng = m.Engine(force_mock=True)
eng.attach(transport.MockPad())
time.sleep(0.2)

games = gameprofiles.GameProfiles(presets_mod.PresetStore())

# ---- 1. 纯函数：parse_vib / collect_exes / convert_entry ----
e = officialimport.parse_vib({"IsVibration": True, "VibParams": "0,1,100,110,0",
                              "VibFilter": 30, "PwmScal": 10})
assert e == {"filter": 30, "scale": 10, "stroke": 0, "press": 1, "strength": 100, "freq": 110}, e
assert officialimport.parse_vib({"IsVibration": False, "VibParams": "0,1,1,1,0"}) is None
assert officialimport.parse_vib({"IsVibration": True, "VibParams": "x"}) is None

ex = officialimport.collect_exes({"ProcessGameName": "r5apex",
                                  "ProcessGameNames": ["r5apex_dx12"], "ExeName": ""})
assert ex == ["r5apex", "r5apex_dx12"], ex
ex2 = officialimport.collect_exes({"ProcessGameName": "WRC", "ExeName": "WRC.exe"})
assert ex2 == ["wrc", "wrc.exe"], ex2
conv = officialimport.convert_entry({"Id": 77, "GameName": "EA WRC", "ProcessGameName": "WRC",
                                     "ExeName": "WRC.exe", "IsVibration": True,
                                     "VibParams": "0,1,100,110,0", "VibFilter": 30, "PwmScal": 10,
                                     "Scenes": "阻尼+震动"})
assert conv["vib"]["filter"] == 30 and conv["official"] and not conv["mod_only"], conv
assert conv["exe"] == ["wrc", "wrc.exe"]
assert officialimport.convert_entry({"Id": 1, "GameName": "无进程"}) is None
print("1. convert functions OK")

# ---- 2. import_official：假官方库 → 用户档案 ----
fake_lib = [
    {"Id": 1, "GameName": "EA WRC", "ProcessGameName": "WRC", "ExeName": "WRC.exe",
     "IsVibration": True, "VibParams": "0,1,100,110,0", "VibFilter": 30, "PwmScal": 10,
     "Scenes": "左：刹车阻尼；右：起步震动"},
    {"Id": 2, "GameName": "艾尔登法环", "ProcessGameName": "eldenring",
     "IsVibration": False, "IsNeedDownMod": True,
     "ModDownLoadUrl": "https://example.com/x.zip", "Scenes": "按武器类型突破/震动"},
    {"Id": 3, "GameName": "守望先锋DS", "ProcessGameName": "Overwatch",
     "IsVibration": False, "IsPS5": True},
    {"Id": 4, "GameName": "没进程的", "IsVibration": True, "VibParams": "0,1,1,1,0"},
]
fake_path = os.path.join(_tmp, "fake_official.json")
with open(fake_path, "w", encoding="utf-8") as f:
    json.dump(fake_lib, f, ensure_ascii=False)
r = officialimport.import_official(games, path=fake_path)
# EA WRC 与内置同名且已带官方 vib → 跳过；艾尔登法环（mod_only 无 vib）/守望先锋DS
# （PS5 记录条目）不再导入成壳（2026-09-20：壳曾遮蔽内置适配卡 + Mod 拉起）；
# 没进程的 → convert None。四条全跳过，零壳产出。
assert r["imported"] == 0 and r["updated"] == 0 and r["skipped"] == 3, r
assert not games.match("eldenring.exe") or not games.all().get("eldenring"), "不得产出老头环壳"
# 重复导入：已带官方 vib 的不再动
r2 = officialimport.import_official(games, path=fake_path)
assert r2["imported"] == 0 and r2["updated"] == 0, r2
# 参数变了（官方更新调参）→ 合并升级，且保留用户 preset_id / 自定义 exe
variant = [dict(fake_lib[0], VibParams="7,7,7,7,0", VibFilter=31)]
vpath = os.path.join(_tmp, "variant.json")
with open(vpath, "w", encoding="utf-8") as f:
    json.dump(variant, f, ensure_ascii=False)
before = games.match("wrc.exe")
pid_keep = before.get("preset_id") or ""
r3 = officialimport.import_official(games, path=vpath)
assert r3["updated"] == 1, r3
after = games.match("wrc.exe")
assert after["vib"]["filter"] == 31 and after["vib"]["freq"] == 7, after["vib"]
assert after.get("preset_id", "") == pid_keep, (after.get("preset_id"), pid_keep)
# 官方新进程名并集进来，原有匹配键不丢
assert "wrc" in after["exe"] and "wrc.exe" in after["exe"]
print("2. import_official OK:", r, r3)

# ---- 3. 匹配规范化：带/不带 .exe 都命中 ----
g = games.match("wrc.exe")
assert g and g["name"] == "EA WRC", g
g2 = games.match("wrc")
assert g2 and g2["name"] == "EA WRC"
assert games.match("nothing.exe") is None
print("3. match normalization OK")

# ---- 4. apply_game：vib 档案 → 双侧 gripBind 落账本（用变体合并后的参数） ----
games.apply_game(games.match("wrc.exe"), eng)
time.sleep(0.2)
gb = eng.state["gripBind"]["left"]
assert gb and gb["filter"] == 31 and gb["freq"] == 7 and gb["source"] == "game:EA WRC", gb
assert eng.state["gripBind"]["right"]["strength"] == 7
print("4. apply_game vib OK:", gb)

# ---- 5. 自动切换：进 WRC 出 WRC ----
orig_fg = gameprofiles.foreground_exe
games.foreground = "x.exe"
gameprofiles.foreground_exe = lambda: "wrc.exe"
games.maybe_autoswitch(eng)
time.sleep(0.2)
assert eng.state["gripBind"]["left"], "自动切换应套用 vib"
assert any(e["kind"] == "autoswitch" for e in eng.events), "应有 autoswitch 事件"
# 切到无档案前台 + 通用联动关 → 解绑
gameprofiles.foreground_exe = lambda: "notepad.exe"
games.maybe_autoswitch(eng)
time.sleep(0.2)
assert eng.state["gripBind"]["left"] is None, "切走应解绑"
# 通用联动开 → 无档案前台回落通用参数
games.set_universal_vib(True, eng)
time.sleep(0.2)
gb2 = eng.state["gripBind"]["left"]
assert gb2 and gb2["source"] == "vib:universal" and gb2["filter"] == officialimport.UNIVERSAL_VIB["filter"], gb2
# 通用联动关 → 解绑
games.set_universal_vib(False, eng)
time.sleep(0.2)
assert eng.state["gripBind"]["left"] is None
print("5. autoswitch + universal fallback OK")

# ---- 6. 自定义 exe（特殊版本）：内置档案复制为用户档案并改匹配键 ----
builtin = next(it for it in games.all().values() if it["builtin"])
g3 = games.set_exe(builtin["id"], ["MySpecialEdition.exe"])
assert not g3["builtin"] and g3["exe"] == ["myspecialedition.exe"], g3
assert games.match("MySpecialEdition.EXE")["id"] == g3["id"]
# 内置档案本体不受影响：原 exe 仍命中内置档案（标准版本照常，特殊版本各走各的）
assert games.match(builtin["exe"][0])["id"] == builtin["id"]
try:
    games.set_exe(g3["id"], [])
    assert False, "空 exe 应报错"
except ValueError:
    pass
print("6. custom exe OK")

gameprofiles.foreground_exe = orig_fg
eng.stop()
print("ALL ADAPTATION TESTS PASS")
