# 设置域端点（ADR-029 B6 自 service.py 逐字搬出）：
# 游戏震动修复（原 2026-09-20 案例）/ Mod 管家（ADR-025）/ 系统级设置（开机自启）。
from fastapi import APIRouter
from pydantic import BaseModel

from .common import err


def build_settings_router(ctx):
    r = APIRouter()
    engine = ctx.engine
    games = ctx.games
    mods = ctx.mods
    ingress = ctx.ingress

    # ---------- 游戏震动修复（飞智虚拟手柄抢 XInput 0 号槽，2026-09-20 原神案例） ----------
    # 不是开关是检测：state 反映设备树实况；enabled(活跃)才有"修复"动作，
    # disabled(已禁用)才显示"恢复"；absent=没装空间站驱动，整卡无事发生。
    # ledger 全程留痕（防"无头案"）：临时修复软件退出自动还原，永久修复仅显式点击。
    @r.get("/api/vibfix")
    def vibfix_get():
        import vibfix
        return {"state": vibfix.status(), "service": vibfix.SERVICE,
                "auto": bool(games.vibfix_auto) if games else False,
                "ledger": vibfix.ledger_get()}

    class VibFixSetReq(BaseModel):
        enabled: bool
        mode: str = "temporary"     # temporary=软件退出自动还原 / permanent=持久禁用

    @r.post("/api/vibfix/set")
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

    class VibFixAutoReq(BaseModel):     # 原与游戏档案共用 AutoswitchReq，B5 起模型随各 router 走
        enabled: bool = True

    @r.post("/api/vibfix/auto")
    def vibfix_auto_set(req: VibFixAutoReq):
        if games is None:
            return err(RuntimeError("游戏档案模块未初始化"))
        return {"ok": True, "auto": games.set_vibfix_auto(req.enabled)}

    # ---------- Mod 管家（ADR-025：官方事件级适配的下载/安装/生命周期） ----------
    @r.get("/api/mods")
    def mods_status():
        if mods is None:
            return {"mods": [], "active_gid": None, "ingress": None}
        out = mods.status()
        out["ingress"] = ingress.status() if ingress else None
        return out

    class ModEnableReq(BaseModel):
        enabled: bool

    @r.post("/api/mods/{gid}/install")
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

    @r.post("/api/mods/{gid}/uninstall")
    def mods_uninstall(gid: str):
        if mods is None:
            return err(RuntimeError("Mod 管家未初始化"))
        try:
            mods.uninstall(gid)
            return {"ok": True}
        except Exception as e:
            return err(e)

    @r.post("/api/mods/{gid}/enable")
    def mods_enable(gid: str, req: ModEnableReq):
        if mods is None:
            return err(RuntimeError("Mod 管家未初始化"))
        try:
            return {"ok": True, "enabled": mods.set_enabled(gid, req.enabled)}
        except Exception as e:
            return err(e)

    @r.post("/api/mods/stop")
    def mods_stop():
        """手动停掉当前 Mod（应急，比如 mod 行为异常）。"""
        if mods is None:
            return err(RuntimeError("Mod 管家未初始化"))
        mods.stop_mod()
        return {"ok": True}

    # ---------- 系统级设置（开机自启） ----------
    import os as _os

    @r.get("/api/settings/autostart")
    def autostart_get():
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                val, _ = winreg.QueryValueEx(k, "Apex5Unleashed")
                return {"ok": True, "enabled": True, "command": val}
        except OSError:
            return {"ok": True, "enabled": False, "command": ""}

    class AutostartReq(BaseModel):      # 原与游戏档案共用 AutoswitchReq，B5 起模型随各 router 走
        enabled: bool = True

    @r.post("/api/settings/autostart")
    def autostart_set(req: AutostartReq):
        """开机自启：HKCU\\...\\Run 写 pythonw + run_gui.pyw（用户级，不需要管理员）。"""
        import sys
        import winreg
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            if req.enabled:
                # 本文件在 app/routers/ 下，比原 service.py 多一层目录：三次 dirname 回到 backend/
                gui = _os.path.join(
                    _os.path.dirname(_os.path.dirname(_os.path.dirname(
                        _os.path.abspath(__file__)))),
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

    return r
