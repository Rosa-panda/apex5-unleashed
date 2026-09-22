# REST + WS 服务层（TECH-SPEC §6）。挂前端静态资源的单进程入口由 main.py 组装。
import asyncio
import json
import socket
import time

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import protocol
import rawstream as _rawstream
import screenpack
import appctx
import motionmaster
import routers
import wsbus


def create_app(engine, store, games=None, ui_hooks=None, mods=None, ingress=None):
    app = FastAPI(title="Apex5 Unleashed", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    ctx = appctx.AppContext(engine=engine, store=store, games=games,
                            mods=mods, ingress=ingress, ui_hooks=ui_hooks)

    # WS 事件总线（wsbus.py，ADR-029 B1）：订阅顺序敏感——bus.publish 必须先于
    # 宏录制器（0xEF 事件分发达顺序）
    bus = wsbus.WsBus()
    ctx.bus = bus

    # ---------- API 响应头：no-store ----------
    # FastAPI JSONResponse 不带缓存头，WebView2 会启发式缓存 GET——轮询永远读到
    # 死状态（开关「分不出开没开」的帮凶）。API 一律禁缓存；静态资源（带 hash）不受影响。
    @app.middleware("http")
    async def _api_no_store(request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith("/api"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    engine.subscribe(bus.publish)
    import macro as _macro
    engine.subscribe(_macro.RECORDER.on_event)   # 宏录制器吃 0xEF 位图事件（ADR-021）

    app.on_event("startup")(bus.grab_loop)

    # ---------- 模型 ----------
    class PresetReq(BaseModel):
        name: str
        note: str = ""
        actions: list = []

    def err(e):
        return JSONResponse({"error": str(e)}, status_code=400)

    # ---------- 系统/WS（ADR-029 B2 起 routers 化）----------
    app.include_router(routers.build_system_router(ctx))
    app.include_router(routers.build_ws_router(ctx))

    # ---------- 控制/灯光（ADR-029 B3 起 routers 化）----------
    app.include_router(routers.build_control_router(ctx))
    app.include_router(routers.build_led_router(ctx))

    # ---------- 屏幕（ADR-018 R4 二期。红线：真机烧写必须 confirm=true 且用户知情） ----------
    _screen_pending = {"frames": None, "interval": 100, "name": "", "seconds": 0}

    class ScreenConvertReq(BaseModel):
        data_b64: str                   # GIF/图片文件内容 base64
        name: str = ""
        mode: str = "fill"              # fill/fit/stretch
        target_frames: int = 30         # 等距抽帧目标（0=不抽帧）

    @app.post("/api/screen/convert")
    def screen_convert(req: ScreenConvertReq):
        import base64
        try:
            raw = base64.b64decode(req.data_b64)
            import io
            from PIL import Image
            im = Image.open(io.BytesIO(raw))
            n_frames = getattr(im, "n_frames", 1)
            if n_frames > 1:
                rgb_frames, interval, truncated = screenpack.frames_from_gif(
                    io.BytesIO(raw), req.mode,
                    target=req.target_frames if req.target_frames > 0 else None)
            else:
                rgb_frames, interval, truncated = [screenpack.fit_rgb(im, req.mode)], 100, False
            frames = [screenpack.encode_frame(f) for f in rgb_frames]
            _screen_pending.update(frames=frames, interval=interval,
                                   name=req.name, seconds=screenpack.estimate_seconds(len(frames)))
            return {"ok": True, "frames": len(frames), "interval_ms": interval,
                    "total_frames": n_frames, "truncated": truncated,
                    "seconds": _screen_pending["seconds"]}
        except screenpack.ScreenPackError as e:
            return err(e)
        except Exception as e:
            return err(RuntimeError(f"图片解析失败: {e}"))

    class ScreenFlashReq(BaseModel):
        confirm: bool = False           # 红线闸门：必须显式 true
        restore_default: bool = False

    @app.get("/api/screen/status")
    def screen_status():
        return engine.last_screen_event

    @app.get("/api/screen/flags")
    def screen_flags():
        try:
            return {"ok": True, **engine.screen_get_flags()}
        except Exception as e:
            return err(e)

    class ScreenFlagReq(BaseModel):
        on: bool

    @app.post("/api/screen/animation")
    def screen_animation(req: ScreenFlagReq):
        try:
            engine.screen_set_flag(9, req.on)       # 19/9 动画常亮（息屏显示）
            return {"ok": True, **engine.screen_get_flags()}
        except Exception as e:
            return err(e)

    @app.post("/api/screen/statusbar")
    def screen_statusbar(req: ScreenFlagReq):
        try:
            engine.screen_set_flag(8, req.on)       # 19/8 状态栏常亮
            return {"ok": True, **engine.screen_get_flags()}
        except Exception as e:
            return err(e)

    @app.post("/api/screen/flash")
    def screen_flash(req: ScreenFlashReq):
        if not req.confirm:
            return err(RuntimeError("红线未过：烧写需 confirm=true（ADR-018 R4）"))
        if not _screen_pending["frames"]:
            return err(RuntimeError("先调用 /api/screen/convert 准备帧数据"))
        try:
            engine.screen_flash(_screen_pending["frames"], interval_ms=_screen_pending["interval"],
                                restore_default=req.restore_default)
            return {"ok": True, "frames": len(_screen_pending["frames"]),
                    "seconds": _screen_pending["seconds"]}
        except Exception as e:
            return err(e)

    # ---------- 测试台 ----------
    @app.post("/api/test/pulse")
    def test_pulse():
        engine.test_pulse()
        return {"ok": True}

    # ---------- 拓展键（ADR-019：映射配置区读写 + 测试模式） ----------
    @app.get("/api/extkeys")
    def extkeys_get():
        import extkeys
        try:
            return {"ok": True, "keys": extkeys.MAPPER.read_mapping()}
        except Exception as e:
            return err(e)

    class ExtKeysTestReq(BaseModel):
        on: bool

    @app.post("/api/extkeys/testmode")
    def extkeys_testmode(req: ExtKeysTestReq):
        """测试模式：六键映射到 Gamepad API 可见目标（视图/菜单/LB/RB/L3/R3）；关=还原备份。"""
        import extkeys
        try:
            if req.on:
                return extkeys.MAPPER.set_targets(extkeys.TEST_TARGETS)
            return extkeys.MAPPER.restore()
        except Exception as e:
            return err(e)

    # ---------- 宏（ADR-021：板载宏，触发键限六拓展键） ----------
    @app.get("/api/macro/config")
    def macro_config():
        import macro
        try:
            return macro.MANAGER.read()
        except Exception as e:
            return err(e)

    class MacroWriteReq(BaseModel):
        macros: list = []               # [{key_id, type, interval, name, actions:[{t,key,ev}]}]
        unbind: list = []               # 需要还原透传（255）的拓展键名

    @app.post("/api/macro/write")
    def macro_write(req: MacroWriteReq):
        import macro
        try:
            # 宏页与触发键绑定同在 profile blob，一次提交（v3.1 方案，ADR-021 修订）
            return macro.MANAGER.write(req.macros, unbind=req.unbind)
        except Exception as e:
            return err(e)

    @app.post("/api/macro/record/start")
    def macro_record_start():
        import macro
        _raw.demands["macro"] = True     # 录制要吃 0xEF 位图流 → 登记需求开流
        _raw.eval("macro-rec")
        macro.RECORDER.start()
        return {"ok": True}

    @app.post("/api/macro/record/stop")
    def macro_record_stop():
        import macro
        _raw.demands["macro"] = False    # 撤需求；流是否关由 _raw.eval 按其余消费者决
        _raw.eval("macro-rec-end")
        return {"ok": True, **macro.RECORDER.stop()}

    @app.get("/api/macro/record/status")
    def macro_record_status():
        import macro
        return macro.RECORDER.status()

    @app.post("/api/macro/backup")
    def macro_backup():
        import macro
        try:
            return {"ok": True, **macro.MANAGER.backup()}
        except Exception as e:
            return err(e)

    @app.post("/api/macro/restore")
    def macro_restore():
        import macro
        try:
            return macro.MANAGER.restore()
        except Exception as e:
            return err(e)

    class SineReq(BaseModel):
        seconds: float = 3.0
        freq: float = 3.0
        amp: int = 220

    @app.post("/api/test/sine")
    def test_sine(req: SineReq):
        engine.test_sine(req.seconds, req.freq, req.amp)
        return {"ok": True}

    @app.post("/api/test/attrib")
    def test_attrib():
        """拓展键受控校准：每键独立时间窗采集 bit→键名归因（进度走 WS attrib 事件）。"""
        import keymonitor
        mon = keymonitor.GamepadRawMonitor.ACTIVE
        if mon is None:
            return JSONResponse({"error": "游戏盘原始监听未运行（mock 模式或设备未连）"}, status_code=400)
        if not mon.start_attribution():
            return JSONResponse({"error": "校准已在进行中"}, status_code=409)
        return {"ok": True}

    @app.get("/api/test/keymap")
    def test_keymap():
        import keymonitor
        mon = keymonitor.GamepadRawMonitor.ACTIVE
        return {"running": bool(mon and mon._attrib_running),
                "labels": {f"b{b}.{bit}": name for (b, bit), name in load_labels_items()}}

    def load_labels_items():
        import keymonitor
        try:
            mon = keymonitor.GamepadRawMonitor.ACTIVE
            if mon:
                return mon._labels.items()
        except Exception:
            pass
        return keymonitor.load_labels().items()

    # ---------- 预设 ----------
    @app.get("/api/presets")
    def presets_list():
        return store.list()

    @app.post("/api/presets")
    def presets_save(req: PresetReq):
        try:
            return {"ok": True, "preset": store.save(req.model_dump())}
        except Exception as e:
            return err(e)

    @app.post("/api/presets/{pid}/apply")
    def presets_apply(pid: str):
        try:
            return {"ok": True, "result": store.apply(pid, engine)}
        except Exception as e:
            return err(e)

    @app.delete("/api/presets/{pid}")
    def presets_delete(pid: str):
        try:
            store.delete(pid)
            return {"ok": True}
        except Exception as e:
            return err(e)

    # ---------- 游戏档案 ----------
    class GameReq(BaseModel):
        name: str
        exe: list[str]
        preset_id: str = ""
        note: str = ""

    class LinkReq(BaseModel):
        preset_id: str = ""

    class AutoswitchReq(BaseModel):
        enabled: bool = True

    @app.get("/api/games")
    def games_list():
        if games is None:
            return {"builtin": [], "user": [], "foreground": None, "autoswitch": True,
                    "universal_vib": False}
        return games.list()

    @app.post("/api/games")
    def games_save(req: GameReq):
        try:
            return {"ok": True, "game": games.save(req.model_dump())}
        except Exception as e:
            return err(e)

    @app.delete("/api/games/{gid}")
    def games_delete(gid: str):
        try:
            games.delete(gid)
            return {"ok": True}
        except Exception as e:
            return err(e)

    @app.post("/api/games/{gid}/apply")
    def games_apply(gid: str):
        try:
            g = games.all().get(gid)
            if not g:
                raise KeyError(gid)
            if not (g.get("vib") or g.get("preset_id")):
                return err(ValueError("该档案无震动联动参数且未绑定预设"))
            games.apply_game(g, engine)
            return {"ok": True, "result": {"applied": g["name"],
                                           "vib": bool(g.get("vib")),
                                           "preset": g.get("preset_id") or ""}}
        except Exception as e:
            return err(e)

    class ExeReq(BaseModel):
        exe: list[str]

    @app.post("/api/games/{gid}/exe")
    def games_set_exe(gid: str, req: ExeReq):
        """自定义 exe 定位（特殊版本游戏，ADR-017）。"""
        try:
            return {"ok": True, "game": games.set_exe(gid, req.exe)}
        except Exception as e:
            return err(e)

    @app.post("/api/games/import-official")
    def games_import_official():
        """导入官方逐游戏适配库（读本机空间站 adapterTriggerGames.json）。"""
        import officialimport
        try:
            return {"ok": True, "result": officialimport.import_official(games)}
        except Exception as e:
            return err(e)

    @app.get("/api/games/official-src")
    def games_official_src():
        import officialimport
        return {"available": bool(officialimport.official_path()),
                "path": officialimport.official_path() or officialimport.OFFICIAL_JSON}

    class UniversalVibReq(BaseModel):
        enabled: bool

    @app.post("/api/vib/universal")
    def vib_universal(req: UniversalVibReq):
        """通用震动联动：游戏震动→扳机反馈（设备端固件路由，任何游戏生效）。"""
        try:
            return {"ok": True, "universal_vib": games.set_universal_vib(req.enabled, engine)}
        except Exception as e:
            return err(e)

    @app.post("/api/games/{gid}/link")
    def games_link(gid: str, req: LinkReq):
        try:
            all_ = games.all()
            if gid not in all_:
                raise KeyError(gid)
            g = all_[gid]
            if g["builtin"]:
                # 内置档案：复制为用户档案再改，保持内置只读
                g = games.save({"name": g["name"], "exe": g["exe"],
                                "note": g.get("note", ""), "preset_id": req.preset_id})
            else:
                g["preset_id"] = req.preset_id
                games.save(g)
            return {"ok": True, "game": g}
        except Exception as e:
            return err(e)

    @app.post("/api/autoswitch")
    def autoswitch_set(req: AutoswitchReq):
        return {"ok": True, "autoswitch": games.set_autoswitch(req.enabled)}

    # ---------- 游戏震动修复（飞智虚拟手柄抢 XInput 0 号槽，2026-09-20 原神案例） ----------
    # 不是开关是检测：state 反映设备树实况；enabled(活跃)才有"修复"动作，
    # disabled(已禁用)才显示"恢复"；absent=没装空间站驱动，整卡无事发生。
    # ledger 全程留痕（防"无头案"）：临时修复软件退出自动还原，永久修复仅显式点击。
    @app.get("/api/vibfix")
    def vibfix_get():
        import vibfix
        return {"state": vibfix.status(), "service": vibfix.SERVICE,
                "auto": bool(games.vibfix_auto) if games else False,
                "ledger": vibfix.ledger_get()}

    class VibFixSetReq(BaseModel):
        enabled: bool
        mode: str = "temporary"     # temporary=软件退出自动还原 / permanent=持久禁用

    @app.post("/api/vibfix/set")
    def vibfix_set(req: VibFixSetReq):
        import vibfix
        try:
            if req.enabled:
                ok = vibfix.restore()
            elif req.mode == "permanent":
                ok = vibfix.fix_permanent()
            else:
                ok = vibfix.fix_temporary()
            if not ok:
                return err(RuntimeError("未获得系统授权（UAC 点了「否」），未做任何更改"))
            return {"ok": True, "state": vibfix.status()}
        except Exception as e:
            return err(e)

    @app.post("/api/vibfix/auto")
    def vibfix_auto_set(req: AutoswitchReq):
        if games is None:
            return err(RuntimeError("游戏档案模块未初始化"))
        return {"ok": True, "auto": games.set_vibfix_auto(req.enabled)}

    # ---------- Mod 管家（ADR-025：官方事件级适配的下载/安装/生命周期） ----------
    @app.get("/api/mods")
    def mods_status():
        if mods is None:
            return {"mods": [], "active_gid": None, "ingress": None}
        out = mods.status()
        out["ingress"] = ingress.status() if ingress else None
        return out

    class ModEnableReq(BaseModel):
        enabled: bool

    @app.post("/api/mods/{gid}/install")
    def mods_install(gid: str):
        if mods is None:
            return err(RuntimeError("Mod 管家未初始化"))
        def on_done(e):
            if e:
                engine._emit("error", detail=f"Mod 安装失败: {e}")
            else:
                engine._emit("mod", state="installed", detail="Mod 安装完成，可在游戏库启用")
        try:
            mods.install(gid, on_done=on_done)
            return {"ok": True}
        except Exception as e:
            return err(e)

    @app.post("/api/mods/{gid}/uninstall")
    def mods_uninstall(gid: str):
        if mods is None:
            return err(RuntimeError("Mod 管家未初始化"))
        try:
            mods.uninstall(gid)
            return {"ok": True}
        except Exception as e:
            return err(e)

    @app.post("/api/mods/{gid}/enable")
    def mods_enable(gid: str, req: ModEnableReq):
        if mods is None:
            return err(RuntimeError("Mod 管家未初始化"))
        try:
            return {"ok": True, "enabled": mods.set_enabled(gid, req.enabled)}
        except Exception as e:
            return err(e)

    @app.post("/api/mods/stop")
    def mods_stop():
        """手动停掉当前 Mod（应急，比如 mod 行为异常）。"""
        if mods is None:
            return err(RuntimeError("Mod 管家未初始化"))
        mods.stop_mod()
        return {"ok": True}

    # ---------- 系统级设置（开机自启 / 封面缓存 / 数据目录） ----------
    import os as _os

    @app.get("/api/settings/autostart")
    def autostart_get():
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                val, _ = winreg.QueryValueEx(k, "Apex5Unleashed")
                return {"ok": True, "enabled": True, "command": val}
        except OSError:
            return {"ok": True, "enabled": False, "command": ""}

    @app.post("/api/settings/autostart")
    def autostart_set(req: AutoswitchReq):
        """开机自启：HKCU\\...\\Run 写 pythonw + run_gui.pyw（用户级，不需要管理员）。"""
        import sys
        import winreg
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            if req.enabled:
                gui = _os.path.join(
                    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                    "run_gui.pyw")
                if not _os.path.isfile(gui):
                    raise FileNotFoundError(gui)
                cmd = f'"{sys.executable}" "{gui}"'
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0,
                                    winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, "Apex5Unleashed", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0,
                                        winreg.KEY_SET_VALUE) as k:
                        winreg.DeleteValue(k, "Apex5Unleashed")
                except FileNotFoundError:
                    pass
            return autostart_get()
        except Exception as e:
            return err(e)

    # ---------- 体验区（ADR-026：隐藏功能孵化区） ----------
    import explab as _explab
    _exp_verdicts = _explab.Verdicts()

    class ExpVerdictReq(BaseModel):
        id: str
        verdict: str          # good / bad / pending
        note: str = ""

    @app.get("/api/exp")
    def exp_list():
        """注册表 + 判定合并下发：前端卡片全靠这里渲染，不硬编码。"""
        feats = []
        for f in _explab.FEATURES:
            v = _exp_verdicts.get(f["id"])
            feats.append({**f, "tierLabel": _explab.TIER_LABEL[f["tier"]],
                          "verdict": v.get("verdict", "pending"),
                          "note": v.get("note", "")})
        return {"ok": True, "features": feats, "summary": _exp_verdicts.summary()}

    @app.post("/api/exp/verdict")
    def exp_verdict(req: ExpVerdictReq):
        """真机测试后的判定留痕：转正/淘汰的证据链。"""
        if not any(f["id"] == req.id for f in _explab.FEATURES):
            return err(ValueError(f"未知体验区功能: {req.id}"))
        try:
            v = _exp_verdicts.set(req.id, req.verdict, req.note)
        except Exception as e:
            return err(e)
        return {"ok": True, "id": req.id, **v, "summary": _exp_verdicts.summary()}

    # ---------- 体验区·功能端点（ADR-027：全部 15 项软件成品） ----------
    # 真机类操作都走 profile/devcfg（Pad 第二句柄或引擎问答），mock 模式直接 400。
    import devcfg as _devcfg
    import diag as _diag
    import dsu as _dsu
    import profile as _profile
    import gamesim as _gamesim_mod
    import maze as _maze
    import rgbbridge as _rgbbridge
    import sharecode as _sharecode
    import softmap as _softmap

    _settings_writer = _devcfg.SettingsWriter(engine)
    _rgb = _rgbbridge.RgbBridge(engine)
    _diag_svc = _diag.Diagnostics(engine)
    _maze_svc = _maze.SERVICE
    _dsu_svc = _dsu.DsuServer(engine)
    _gamesim = _gamesim_mod.GameSim(lambda: ingress, lambda: _rgb)
    engine.subscribe_motion(_maze_svc.on_motion)   # 弹珠迷宫的倾斜源（0xEF 运动流）
    engine.subscribe_motion(_dsu_svc.on_motion)    # 模拟器体感桥（DSU/Cemuhook，#18）

    # ---- 0xEF 流按需开关（ADR-028 修订 2）：需求登记表独立模块（rawstream.py），
    # service 只做端点接线，决策/心跳/看门狗全在 RawStreamHub ----
    _raw = _rawstream.RawStreamHub(engine)

    # ---- 体感中心总闸（motionmaster.py，ADR-029 B1 抽出；原 ADR-028）----
    # 构造内完成：持久态恢复（DSU start → _raw.eval）+ 看门狗启动 + motion_to_ws
    # 订阅（30Hz 节流，总闸静默）——原 791-857 行序逐字保留
    _mm = motionmaster.MotionMaster(engine, bus, _dsu_svc, _maze_svc, _softmap.HUB, _raw)
    ctx.mm = _mm
    ctx.raw = _raw

    if ingress:
        ingress.on_applied = _rgb.on_game_event    # Mod 扳机事件 → 闪灯联动
    engine.subscribe_motion(_softmap.HUB.on_motion)
    engine.subscribe_motion(_diag_svc.on_motion)
    engine.subscribe(_softmap.HUB.on_key)

    def _require_real():
        if engine.force_mock or engine.dev_kind != "real":
            raise RuntimeError("此操作需要真机连接（mock 模式不可用）")

    class ExpTurboReq(BaseModel):
        kid: int
        mode: int            # 0 关 / 1 按住连发 / 2 开关切换
        freq: int = 10

    class ExpStickReq(BaseModel):
        side: str
        preset: int | None = None
        center: int = 0
        edge: int = 0
        p1: list[int] = [63, 63]
        p2: list[int] = [127, 127]
        is_round: bool | None = None

    class ExpTriggerCurveReq(BaseModel):
        side: str
        zero: int = 0
        end: int = 255

    class ExpMotionReq(BaseModel):
        target: int
        enable_key: int = 255
        enable_type: int = 0
        dead_zone: int = 10
        sens_x: int = 50
        sens_y: int = 50

    class ExpGripVibReq(BaseModel):
        enabled: bool
        left: dict = {}
        right: dict = {}

    class ExpTitleReq(BaseModel):
        title: str

    class ExpSettingReq(BaseModel):
        op: str              # bit / rate / precision / sensitivity / sleep
        sub: int | None = None
        on: bool | None = None
        value: int | None = None

    class ExpNicknameReq(BaseModel):
        name: str

    class ExpSlotReq(BaseModel):
        slot: int
        confirm: str = ""

    class ExpShareReq(BaseModel):
        code: str = ""
        kind: str = "profile"
        blob_hex: str = ""

    class ExpGyroReq(BaseModel):
        patch: dict = {}

    class ExpRgbReq(BaseModel):
        enabled: bool
        port: int = 7878
        flash: bool = None            # 游戏事件（Mod 扳机流）→ 闪灯，None=不改动

    class ExpRgbTestReq(BaseModel):
        rgb: list = [255, 0, 0]

    class ExpRgbFlashReq(BaseModel):
        enabled: bool
        rgb: list = [255, 0, 0]

    class ExpSimReq(BaseModel):
        scenario: str = "idle"

    class ExpMazeReq(BaseModel):
        op: str = "calibrate"

    class ExpDsuReq(BaseModel):
        enabled: bool
        port: int = 26760
        invert: list = None           # [pitch, yaw, roll]，None=不改动

    class ExpImuReq(BaseModel):
        enabled: bool

    class MotionMasterReq(BaseModel):
        enabled: bool

    class ExpDiagReq(BaseModel):
        op: str              # sample / adccalib / autocal
        seconds: float = 5.0
        stage: str = "start"
        on: bool = False

    @app.get("/api/exp/profile")
    def exp_profile_read():
        try:
            _require_real()
            return {"ok": True, **_profile.SERVICE.read_profile()}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/profile/turbo")
    def exp_profile_turbo(req: ExpTurboReq):
        try:
            _require_real()
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_turbo(b, req.kid, req.mode, req.freq))}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/profile/stick")
    def exp_profile_stick(req: ExpStickReq):
        try:
            _require_real()
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_stick(b, req.side, req.preset, req.center, req.edge,
                                             tuple(req.p1), tuple(req.p2), req.is_round))}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/profile/trigger-curve")
    def exp_profile_trigger(req: ExpTriggerCurveReq):
        try:
            _require_real()
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_trigger_curve(b, req.side, req.zero, req.end))}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/profile/motion")
    def exp_profile_motion(req: ExpMotionReq):
        """体感固件层（与软件层体感互斥——UI 负责，后端两边各自拦 enabled）。"""
        try:
            _require_real()
            if req.target != _profile.MOTION_OFF and _softmap.HUB.gyro.cfg["enabled"]:
                raise RuntimeError("软件层体感瞄准开着，先关掉再启用固件层（互斥）")
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_motion(b, req.target, req.enable_key,
                                              req.enable_type, req.dead_zone,
                                              req.sens_x, req.sens_y))}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/profile/gripvib")
    def exp_profile_gripvib(req: ExpGripVibReq):
        try:
            _require_real()
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_grip_vib(b, req.enabled, req.left, req.right))}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/profile/title")
    def exp_profile_title(req: ExpTitleReq):
        try:
            _require_real()
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_title(b, req.title))}
        except Exception as e:
            return err(e)

    @app.get("/api/exp/slots")
    def exp_slots():
        try:
            _require_real()
            return {"ok": True, **_profile.SERVICE.read_slots()}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/slots/apply")
    def exp_slots_apply(req: ExpSlotReq):
        try:
            _require_real()
            return {"ok": True, **_profile.SERVICE.apply_slot(req.slot)}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/profile/switch")
    def exp_profile_switch(req: ExpSlotReq):
        try:
            _require_real()
            return {"ok": True, **_profile.SERVICE.sync_switch(req.slot)}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/factoryreset/slot")
    def exp_factory_slot(req: ExpSlotReq):
        if req.confirm != "RESET":
            return err(ValueError("确认字符串不符（须输入 RESET）"))
        try:
            _require_real()
            _full_backup()
            return {"ok": True, **_profile.SERVICE.factory_reset_slot(req.slot)}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/factoryreset/all")
    def exp_factory_all(req: ExpSlotReq):
        if req.confirm != "RESET-ALL":
            return err(ValueError("确认字符串不符（须输入 RESET-ALL）"))
        try:
            _require_real()
            _full_backup()
            return {"ok": True, **_profile.SERVICE.factory_reset_all()}
        except Exception as e:
            return err(e)

    def _full_backup():
        """危险操作前的全量备份：四槽 blob + 灯表 → %APPDATA%\\Apex5Unleashed\\backup_<ts>\\。"""
        import os
        import time
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "Apex5Unleashed",
                         "backup_" + time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(d, exist_ok=True)
        import extkeys
        with _profile.SERVICE._lock:
            pad = extkeys.Pad()
            st = pad.read_status()
            for i in range(_profile.SLOTS):
                blob = _profile.SERVICE._read_live(pad, i)
                with open(os.path.join(d, f"slot{i}.bin"), "wb") as f:
                    f.write(bytes(blob))
        try:
            engine.led_backup(os.path.join(d, "led.bin"))
        except Exception:
            pass
        with open(os.path.join(d, "README.txt"), "w", encoding="utf-8") as f:
            f.write(f"恢复出厂前自动全量备份 {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"slot0-3.bin=档案blob  led.bin=灯表（读不到则无此文件）\n")
        return d

    @app.get("/api/exp/devcfg")
    def exp_devcfg_read():
        try:
            _require_real()
            out = {"ok": True, "settings": _settings_writer.read(),
                   "nickname": None, "owner": engine.owner,
                   "versions": engine.versions}
            for body in engine.request(_extbuild(2), 2, timeout=0.8, source="devcfg"):
                if body[2] == 2:
                    out["nickname"] = _devcfg.parse_nickname(body)
                    break
            return out
        except Exception as e:
            return err(e)

    def _extbuild(cmd, payload=b""):
        import extkeys
        return extkeys.build(cmd, payload)

    @app.post("/api/exp/devcfg/setting")
    def exp_devcfg_setting(req: ExpSettingReq):
        try:
            _require_real()
            if req.op == "bit":
                if req.sub is None or not 1 <= req.sub <= 10:
                    raise ValueError("sub 1..10")
                s = _settings_writer.write_bit(req.sub, bool(req.on))
            elif req.op == "rate":
                s = _settings_writer.write_rate(req.value)
            elif req.op == "precision":
                s = _settings_writer.write_precision(req.value)
            elif req.op == "sensitivity":
                s = _settings_writer.write_sensitivity(req.value)
            elif req.op == "sleep":
                s = _settings_writer.write_sleep(req.value)
            else:
                raise ValueError("op")
            return {"ok": True, "settings": s}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/devcfg/nickname")
    def exp_devcfg_nickname(req: ExpNicknameReq):
        try:
            _require_real()
            payload = _devcfg.nickname_packet(req.name)
            engine.send_checked(protocol.build(24, payload), 24, source="devcfg")
            name = None
            for body in engine.request(_extbuild(2), 2, timeout=0.8, source="devcfg"):
                if body[2] == 2:
                    name = _devcfg.parse_nickname(body)
                    break
            return {"ok": True, "nickname": name}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/devcfg/reboot")
    def exp_devcfg_reboot():
        try:
            _require_real()
            return _settings_writer.reboot()
        except Exception as e:
            return err(e)

    @app.get("/api/exp/owner")
    def exp_owner():
        try:
            _require_real()
            o = engine.read_owner()
            if o is None:
                raise RuntimeError("cmd16 无回复")
            return {"ok": True, "owner": o}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/owner/acquire")
    def exp_owner_acquire():
        try:
            _require_real()
            return engine.acquire_control()
        except Exception as e:
            return err(e)

    @app.get("/api/exp/gyro")
    def exp_gyro_status():
        return {"ok": True, **_softmap.HUB.gyro.status()}

    @app.post("/api/exp/gyro")
    def exp_gyro_config(req: ExpGyroReq):
        try:
            # 与固件层互斥：/exp/profile/motion 开固件层时会反向拦软件层；这里开软件层
            # 时固件层状态读档案代价高，由 UI 提示承担（两端文案都有互斥警告）。
            return {"ok": True, **_softmap.HUB.gyro.set_config(dict(req.patch))}
        except Exception as e:
            return err(e)

    @app.get("/api/exp/stickmap")
    def exp_stickmap_status():
        return {"ok": True, **_softmap.HUB.stickmap.status()}

    @app.post("/api/exp/stickmap")
    def exp_stickmap_config(req: ExpGyroReq):
        try:
            return {"ok": True, **_softmap.HUB.stickmap.set_config(dict(req.patch))}
        except Exception as e:
            return err(e)

    @app.get("/api/exp/rgbbridge")
    def exp_rgb_status():
        return {"ok": True, **_rgb.status()}

    @app.post("/api/exp/rgbbridge")
    def exp_rgb_config(req: ExpRgbReq):
        try:
            if req.flash is not None:
                _rgb.set_flash(req.flash)
            if req.enabled:
                return {"ok": True, **_rgb.start(req.port)}
            return {"ok": True, **_rgb.stop()}
        except Exception as e:
            return err(e)

    @app.get("/api/exp/maze")
    def exp_maze_status():
        return {"ok": True, **_maze_svc.status()}

    @app.post("/api/exp/maze")
    def exp_maze_op(req: ExpMazeReq):
        try:
            if req.op == "calibrate":
                _maze_svc.calibrate()
                return {"ok": True, **_maze_svc.status()}
            return err(f"未知操作：{req.op}")
        except Exception as e:
            return err(e)

    @app.get("/api/exp/dsu")
    def exp_dsu_status():
        return {"ok": True, **_dsu_svc.status()}

    @app.post("/api/exp/dsu")
    def exp_dsu_config(req: ExpDsuReq):
        try:
            if req.invert is not None:
                if len(req.invert) != 3:
                    return err("invert 需要 [pitch, yaw, roll] 三个布尔值")
                _dsu_svc.set_invert(*req.invert)
            if req.enabled:
                _dsu_svc.start(req.port)
            else:
                _dsu_svc.stop()
            return {"ok": True, **_dsu_svc.status()}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/imu")
    def exp_imu_toggle(req: ExpImuReq):
        """0xEF 运动流手动开关（无 UI，调试用）：走需求登记表 manual 位。"""
        try:
            _require_real()
            _raw.demands["manual"] = bool(req.enabled)
            on = _raw.eval("manual")
            return {"ok": True, "raw": on}
        except Exception as e:
            return err(e)

    @app.post("/api/rawstream")
    def rawstream_heartbeat(req: dict):
        """拓展键监听心跳（ADR-028 修订 2）：前端测试页打开监听时每 15s 打卡，
        padlive 新鲜（<30s）才保持 0xEF 流开——页面关了/断网 30s 内自动收流，
        手柄恢复可休眠。"""
        try:
            _raw.heartbeat(bool(req.get("on", True)))
            on = _raw.eval("padlive")
            return {"ok": True, "on": bool(req.get("on", True)), "raw": on}
        except Exception as e:
            return err(e)

    # ---- 体感中心总闸端点（状态机在 motionmaster.py）----
    @app.get("/api/motion/master")
    def motion_master_get():
        _mm.hits["get"] += 1
        return _mm.status()

    @app.post("/api/motion/master")
    def motion_master_set(req: MotionMasterReq):
        t0 = time.monotonic()
        _mm.hits["post"] += 1
        _mm.log(f"POST enabled={req.enabled}")
        note = None
        try:
            if req.enabled:
                try:
                    _dsu_svc.start()
                except Exception as e:
                    note = f"DSU 桥启动失败（体感其余功能不受影响）：{e}"
            else:
                # 撤总闸需求：桥+瞄准+体感 UI 推送全关；流是否关由 _raw.eval
                # 按其余消费者（宏录制/拓展键监听）决——没人用即收流，手柄可休眠
                _dsu_svc.stop()
                try:
                    _softmap.HUB.gyro.set_config({"enabled": False})
                except Exception:
                    pass
            _mm.hub["master"] = bool(req.enabled)
            _raw.demands["master"] = bool(req.enabled)
            _raw.eval("master-set" if req.enabled else "master-clear")
            _mm.save(req.enabled)
            _mm.log(f"POST done {req.enabled} in {(time.monotonic() - t0) * 1000:.0f}ms")
            return _mm.status(note)
        except Exception as e:
            _mm.log(f"POST error {req.enabled}: {e}")
            return err(e)

    @app.get("/api/exp/gamesim")
    def exp_gamesim_status():
        return {"ok": True, **_gamesim.status()}

    @app.post("/api/exp/gamesim")
    def exp_gamesim_run(req: ExpSimReq):
        try:
            if req.scenario == "stop":
                _gamesim.stop()
                return {"ok": True, **_gamesim.status()}
            return {"ok": True, **_gamesim.start(req.scenario)}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/rgbbridge/flash")
    def exp_rgb_flash(req: ExpRgbFlashReq):
        try:
            _rgb.set_flash(req.enabled, req.rgb)
            return {"ok": True, **_rgb.status()}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/rgbbridge/test")
    def exp_rgb_test(req: ExpRgbTestReq):
        """本机往桥发一包颜色，走完整链路（UDP→解析→限频→写灯），让用户直接看到效果。"""
        try:
            if not _rgb.enabled:
                raise RuntimeError("桥未启动，先点启动")
            r, g, b = (int(x) for x in req.rgb)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.sendto(f"{r},{g},{b}".encode("ascii"), ("127.0.0.1", _rgb.port))
            finally:
                s.close()
            time.sleep(1.2)          # 越过 1s 限频窗口再看统计
            return {"ok": True, "sent": [r, g, b], **_rgb.status()}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/sharecode/encode")
    def exp_share_encode(req: ExpShareReq):
        try:
            if req.kind == "profile":
                _require_real()
                import extkeys as _ek
                with _profile.SERVICE._lock:
                    pad = _ek.Pad()
                    st = pad.read_status()
                    blob = _profile.SERVICE._read_live(pad, req.slot if hasattr(req, "slot") else st["active"])
                payload = {"kind": "profile", "slot": st["active"], "blob": bytes(blob).hex()}
            elif req.kind == "blob":
                if not req.blob_hex:
                    raise ValueError("blob_hex 为空")
                payload = {"kind": "profile", "blob": req.blob_hex.replace(" ", "")}
            else:
                raise ValueError(f"未知分享类型: {req.kind}")
            return {"ok": True, "code": _sharecode.encode(payload)}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/sharecode/decode")
    def exp_share_decode(req: ExpShareReq):
        try:
            data = _sharecode.decode(req.code)
            out = {"ok": True, "kind": data.get("kind"), "slot": data.get("slot")}
            if "blob" in data:
                blob = bytes.fromhex(data["blob"])
                if len(blob) != 840:
                    raise ValueError(f"blob 长度异常（{len(blob)}B，应为 840）")
                out["profile"] = _profile.parse_profile(blob)
            return out
        except Exception as e:
            return err(e)

    @app.post("/api/exp/sharecode/apply")
    def exp_share_apply(req: ExpShareReq):
        try:
            _require_real()
            data = _sharecode.decode(req.code)
            if data.get("kind") != "profile" or "blob" not in data:
                raise ValueError("只支持档案分享码")
            blob = bytearray(bytes.fromhex(data["blob"]))
            if len(blob) != 840:
                raise ValueError(f"blob 长度异常（{len(blob)}B）")

            def _overwrite(b, src=bytes(blob)):
                b[:] = src
            return {"ok": True, **_profile.SERVICE.edit(_overwrite)}
        except Exception as e:
            return err(e)

    @app.post("/api/exp/diagnostics")
    def exp_diagnostics(req: ExpDiagReq):
        try:
            _require_real()
            if req.op == "sample":
                return {"ok": True, **_diag_svc.sample(req.seconds)}
            if req.op == "adccalib":
                return {"ok": True, **_diag_svc.adc_calib(req.stage)}
            if req.op == "autocal":
                return {"ok": True, **_diag_svc.autocal(req.on)}
            raise ValueError("op")
        except Exception as e:
            return err(e)

    @app.get("/api/exp/diagnostics")
    def exp_diagnostics_data():
        return {"ok": True, **_diag_svc.sampler.data()}

    @app.get("/api/imgcache/status")
    def imgcache_status():
        import gameimg
        return {"ok": True, **gameimg.cache_stats()}

    @app.post("/api/imgcache/clear")
    def imgcache_clear():
        import gameimg
        freed = gameimg.cache_clear()
        return {"ok": True, "freed_bytes": freed}

    # ---------- 封面图本地代理（gameimg 后台预下载，前端不走外链 CDN） ----------
    import gameimg

    @app.get("/api/game-img/{gid}")
    def game_img(gid: str):
        p = gameimg.cached_path(gid)
        if p:
            return FileResponse(p, headers={"Cache-Control": "public, max-age=604800"})
        # 还没下好：404 + no-store，前端拿到后延迟重试（下载完下次重试即命中）
        return JSONResponse({"error": "pending"}, status_code=404,
                            headers={"Cache-Control": "no-store"})

    # ---------- 事件流 ----------
    # /ws 已在 B2 随 routers/ws.py 挂载（bus.attach）

    return app
