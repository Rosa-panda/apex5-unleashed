# REST + WS 服务层（TECH-SPEC §6）。挂前端静态资源的单进程入口由 main.py 组装。
import asyncio
import json

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import protocol
import screenpack


def create_app(engine, store, games=None, ui_hooks=None, mods=None, ingress=None):
    app = FastAPI(title="Apex5 Unleashed", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/favicon.ico")
    def favicon():
        """页内图标：与窗口/托盘同源的自绘手柄（icon.py，静态挂载前注册故优先命中）。
        ⚠ 必须全内存生成，禁止碰 app.ico 文件——窗口 loaded 事件里 Icon(path) 在读
        同一文件，favicon 每次重写会和它撞车：.NET 原生读卡死不释放 GIL，全进程僵死
        （py-spy 实锤两线程冻结数分钟、uvicorn 拒应答，2026-09-20）。"""
        import io
        from fastapi.responses import Response
        import icon
        try:
            buf = io.BytesIO()
            icon.pad_image("self", 64).save(buf, format="ICO",
                                            sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
            return Response(content=buf.getvalue(), media_type="image/x-icon",
                            headers={"Cache-Control": "public, max-age=86400"})
        except Exception:
            raise HTTPException(404)

    clients = set()
    loop_ref = {"loop": None}

    def bus_to_ws(evt):
        """引擎线程 → 事件循环线程安全投递。"""
        loop = loop_ref["loop"]
        if loop is None:
            return
        for q in list(clients):
            def deliver(q=q):
                try:
                    q.put_nowait(evt)
                except asyncio.QueueFull:
                    pass
            try:
                loop.call_soon_threadsafe(deliver)
            except RuntimeError:
                pass

    engine.subscribe(bus_to_ws)
    import macro as _macro
    engine.subscribe(_macro.RECORDER.on_event)   # 宏录制器吃 0xEF 位图事件（ADR-021）

    @app.on_event("startup")
    async def _grab_loop():
        loop_ref["loop"] = asyncio.get_running_loop()

    # ---------- 模型 ----------
    class TriggerReq(BaseModel):
        side: str
        mode: str
        params: dict = {}
        preview: bool = False
        apply: bool = True          # False = 仅预览（不落账本）

    class RumbleReq(BaseModel):
        l: int = 0
        r: int = 0
        duration: float | None = None

    class GripReq(BaseModel):
        side: str
        params: dict = {}

    class PresetReq(BaseModel):
        name: str
        note: str = ""
        actions: list = []

    def err(e):
        return JSONResponse({"error": str(e)}, status_code=400)

    # ---------- 基础 ----------
    @app.get("/api/health")
    def health():
        return {"ok": True, "mock": engine.force_mock, "online": engine.online}

    class UiErrorReq(BaseModel):
        msg: str = ""
        stack: str = ""
        where: str = ""

    @app.post("/api/ui-error")
    def ui_error(req: UiErrorReq):
        """前端渲染崩溃上报（黑屏诊断）：落 stderr/apex5.log。"""
        import sys
        print(f"[UI-ERROR] {req.where}: {req.msg}\n{req.stack}", file=sys.stderr, flush=True)
        return {"ok": True}

    @app.get("/api/show")
    def show_window():
        """二次启动唤起：新实例探测到本实例后调这里，把已开的窗口拉到前台。"""
        cb = (ui_hooks or {}).get("show")
        if cb:
            try:
                cb()
            except Exception:
                pass
        return {"ok": True}

    @app.get("/api/device")
    def device():
        return {"kind": engine.dev_kind, "online": engine.online,
                "vid": f"{protocol.VID:04X}", "pid": f"{protocol.PID:04X}"}

    @app.get("/api/state")
    def state():
        return engine.snapshot()

    @app.get("/api/modes")
    def modes():
        return {"trigger": {m: [f[0] for f in s["fields"]] for m, s in protocol.TRIGGER_MODES.items()},
                "grip": [f[0] for f in protocol.GRIP_FIELDS]}

    # ---------- 控制 ----------
    @app.post("/api/trigger")
    def trigger(req: TriggerReq):
        try:
            engine.set_trigger(req.side, req.mode, req.params,
                               preview=not req.apply, source="ui")
            return {"ok": True}
        except Exception as e:
            return err(e)

    @app.post("/api/trigger/clear")
    def trigger_clear(req: TriggerReq):
        try:
            for s in (["left", "right"] if req.side == "both" else [req.side]):
                engine.clear_trigger(s, source="ui")
            return {"ok": True}
        except Exception as e:
            return err(e)

    @app.post("/api/rumble")
    def rumble(req: RumbleReq):
        try:
            engine.set_rumble(req.l, req.r, req.duration, source="ui")
            return {"ok": True}
        except Exception as e:
            return err(e)

    @app.post("/api/grip")
    def grip(req: GripReq):
        try:
            engine.bind_grip(req.side, req.params, source="ui")
            return {"ok": True}
        except Exception as e:
            return err(e)

    @app.post("/api/grip/unbind")
    def grip_unbind(req: GripReq):
        try:
            for s in (["left", "right"] if req.side == "both" else [req.side]):
                engine.unbind_grip(s, source="ui")
            return {"ok": True}
        except Exception as e:
            return err(e)

    @app.post("/api/panic")
    def panic():
        engine.panic(source="ui")
        return {"ok": True}

    @app.post("/api/proxy/reclaim")
    def proxy_reclaim():
        engine.reclaim()
        return {"ok": True}

    # ---------- 灯光（ADR-018） ----------
    class LedTestReq(BaseModel):
        r: int = 255
        g: int = 0
        b: int = 0

    @app.post("/api/led/test")
    def led_test(req: LedTestReq):
        try:
            engine.led_test(req.r, req.g, req.b)
            return {"ok": True}
        except Exception as e:
            return err(e)

    @app.get("/api/led/config")
    def led_config():
        try:
            bean = engine.led_read_config(source="ui")
            return {"ok": bean is not None, "bean": bean}
        except Exception as e:
            return err(e)

    class LedApplyReq(BaseModel):
        mode: str                       # on/off/breath/gradient/flow/default
        colors: list = [[255, 0, 0]]    # [[r,g,b], ...]
        brightness: int | None = None
        period: int | None = None

    @app.post("/api/led/apply")
    def led_apply(req: LedApplyReq):
        try:
            engine.led_apply_effect(req.mode, [tuple(c) for c in req.colors],
                                    brightness=req.brightness, period=req.period)
            return {"ok": True}
        except Exception as e:
            return err(e)

    @app.post("/api/led/backup")
    def led_backup():
        try:
            return {"ok": True, "path": engine.led_backup()}
        except Exception as e:
            return err(e)

    @app.post("/api/led/restore")
    def led_restore():
        try:
            engine.led_restore()
            return {"ok": True}
        except Exception as e:
            return err(e)

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
        macro.RECORDER.start()
        return {"ok": True}

    @app.post("/api/macro/record/stop")
    def macro_record_stop():
        import macro
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
    @app.get("/api/vibfix")
    def vibfix_get():
        import vibfix
        return {"state": vibfix.status(), "service": vibfix.SERVICE,
                "auto": bool(games.vibfix_auto) if games else False}

    @app.post("/api/vibfix/set")
    def vibfix_set(req: AutoswitchReq):
        import vibfix
        try:
            if not vibfix.set_enabled(req.enabled):
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

    @app.get("/api/imgcache/status")
    def imgcache_status():
        import gameimg
        return {"ok": True, **gameimg.cache_stats()}

    @app.post("/api/imgcache/clear")
    def imgcache_clear():
        import gameimg
        freed = gameimg.cache_clear()
        return {"ok": True, "freed_bytes": freed}

    @app.post("/api/open-folder")
    def open_folder(req: dict = None):
        """打开数据目录（资源管理器）。目录不存在则顺带创建。"""
        base = _os.environ.get("APPDATA") or _os.path.expanduser("~")
        d = _os.path.join(base, "Apex5Unleashed")
        _os.makedirs(d, exist_ok=True)
        _os.startfile(d)                     # noqa: S606 本机 GUI 行为，路径常量
        return {"ok": True, "path": d}

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
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        q = asyncio.Queue(maxsize=200)
        clients.add(q)
        try:
            await ws.send_text(json.dumps({"ts": "", "kind": "snapshot",
                                           **engine.snapshot()}, ensure_ascii=False))
            while True:
                evt = await q.get()
                await ws.send_text(json.dumps(evt, ensure_ascii=False))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            clients.discard(q)

    return app
