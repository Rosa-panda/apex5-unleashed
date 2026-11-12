# 游戏档案端点（ADR-029 B5 自 service.py 逐字搬出；原 ADR-014/017）
from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .common import err


def build_games_router(ctx):
    r = APIRouter()
    games = ctx.games
    engine = ctx.engine

    class GameReq(BaseModel):
        name: str
        exe: list[str]
        note: str = ""

    class AutoswitchReq(BaseModel):
        enabled: bool = True

    @r.get("/api/games")
    def games_list():
        if games is None:
            return {"builtin": [], "user": [], "foreground": None, "autoswitch": True,
                    "universal_vib": False}
        return games.list()

    @r.post("/api/games")
    def games_save(req: GameReq):
        """手动添加游戏：以通用震动参数起步（之后可导出→改参数→再导入）。"""
        from officialimport import UNIVERSAL_VIB
        try:
            return {"ok": True, "game": games.save({**req.model_dump(), "vib": dict(UNIVERSAL_VIB)})}
        except Exception as e:
            return err(e)

    @r.delete("/api/games/{gid}")
    def games_delete(gid: str):
        try:
            games.delete(gid)
            return {"ok": True}
        except Exception as e:
            return err(e)

    @r.post("/api/games/{gid}/apply")
    def games_apply(gid: str):
        try:
            g = games.all().get(gid)
            if not g:
                raise KeyError(gid)
            if not g.get("vib"):
                return err(ValueError("该游戏没有震动联动参数"))
            games.apply_game(g, engine)
            return {"ok": True, "result": {"applied": g["name"], "vib": True}}
        except Exception as e:
            return err(e)

    @r.post("/api/games/import-config")
    def games_import_config(data: dict | list = Body(...)):
        """导入自定义游戏配置（单个对象或数组，格式见 README「自定义适配」）。"""
        try:
            saved = games.import_config(data)
            return {"ok": True, "count": len(saved), "names": [g["name"] for g in saved]}
        except Exception as e:
            return err(e)

    @r.post("/api/games/{gid}/export")
    def games_export(gid: str):
        """导出配置：弹系统「另存为」框写 JSON 文件（WebView 里下载链接不可用）。"""
        import json as _json
        try:
            cfg = games.export_config(gid)
            pick = (ctx.ui_hooks or {}).get("save_file")
            if not pick:
                return {"ok": True, "config": cfg}       # 无窗口：直接返回内容
            path = pick(f"{cfg['name']}.json")
            if not path:
                return {"ok": True, "cancelled": True}
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(cfg, f, ensure_ascii=False, indent=2)
            return {"ok": True, "path": path}
        except Exception as e:
            return err(e)

    class ExeReq(BaseModel):
        exe: list[str]

    @r.post("/api/games/{gid}/exe")
    def games_set_exe(gid: str, req: ExeReq):
        """自定义 exe 定位（特殊版本游戏，ADR-017）。"""
        try:
            return {"ok": True, "game": games.set_exe(gid, req.exe)}
        except Exception as e:
            return err(e)

    @r.post("/api/games/import-official")
    def games_import_official():
        """导入官方逐游戏适配库（读本机空间站 adapterTriggerGames.json）。"""
        import officialimport
        try:
            return {"ok": True, "result": officialimport.import_official(games)}
        except Exception as e:
            return err(e)

    @r.get("/api/games/official-src")
    def games_official_src():
        import officialimport
        p = officialimport.official_path()
        return {"available": bool(p), "path": p or officialimport.OFFICIAL_JSON,
                "custom": officialimport.get_custom()}

    class OfficialSrcReq(BaseModel):
        path: str = ""

    @r.post("/api/games/official-src")
    def games_official_src_set(req: OfficialSrcReq):
        """手动指定官方库位置（解压版空间站）；path 空 = 恢复自动识别。"""
        import officialimport
        try:
            return {"ok": True, "path": officialimport.set_custom(req.path)}
        except Exception as e:
            return err(e)

    @r.post("/api/games/official-src/pick")
    def games_official_src_pick():
        """弹系统选文件夹对话框选空间站目录（WebView 里 <input type=file> 拿不到完整路径）。"""
        import officialimport
        pick = (ctx.ui_hooks or {}).get("pick_folder")
        if not pick:
            return err(RuntimeError("当前无窗口，无法弹出选择框"))
        try:
            chosen = pick()
            if not chosen:
                return {"ok": True, "cancelled": True}
            return {"ok": True, "path": officialimport.set_custom(chosen)}
        except Exception as e:
            return err(e)

    class DisableReq(BaseModel):
        disabled: bool = True

    @r.post("/api/games/{gid}/disable")
    def games_disable(gid: str, req: DisableReq):
        """手动禁用/启用某条适配（同一游戏多条适配时挑掉不想要的，issue #2）。
        生效切换由前台监控下一拍重评（Mod 管家同步停/起）。"""
        try:
            return {"ok": True, "disabled": games.set_disabled(gid, req.disabled)}
        except Exception as e:
            return err(e)

    class UniversalVibReq(BaseModel):
        enabled: bool

    @r.post("/api/vib/universal")
    def vib_universal(req: UniversalVibReq):
        """通用震动联动：游戏震动→扳机反馈（设备端固件路由，任何游戏生效）。"""
        try:
            return {"ok": True, "universal_vib": games.set_universal_vib(req.enabled, engine)}
        except Exception as e:
            return err(e)

    @r.post("/api/arcade/launch")
    def arcade_launch():
        """启动内置演示游戏「扳机猎人」（Rust，源码在 arcade/）。
        打包版随软件放在 arcade/ 下；源码运行时用 arcade/target/release 里自己编译的。"""
        import os
        import subprocess
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))    # app/（frozen 下 = 包根）
        cands = [os.path.join(here, "arcade", "apex5-arcade.exe"),
                 os.path.join(here, "..", "..", "arcade", "target", "release", "apex5-arcade.exe")]
        exe = next((os.path.abspath(p) for p in cands if os.path.isfile(p)), None)
        if not exe:
            return err(FileNotFoundError("没找到 apex5-arcade.exe：源码运行请先在 arcade 目录执行 build.cmd"))
        try:
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
            return {"ok": True, "path": exe}
        except Exception as e:
            return err(e)

    class FeedbackReq(BaseModel):
        enabled: bool = True

    @r.post("/api/feedback")
    def feedback_set(req: FeedbackReq):
        """适配生效时手柄短震一下（全屏游戏里确认用）。"""
        return {"ok": True, "feedback": games.set_feedback(req.enabled)}

    @r.post("/api/autoswitch")
    def autoswitch_set(req: AutoswitchReq):
        return {"ok": True, "autoswitch": games.set_autoswitch(req.enabled)}

    # ---------- 封面图本地代理（gameimg 后台预下载，前端不走外链 CDN） ----------
    import gameimg

    @r.get("/api/game-img/{gid}")
    def game_img(gid: str):
        p = gameimg.cached_path(gid)
        if p:
            return FileResponse(p, headers={"Cache-Control": "public, max-age=604800"})
        # 还没下好：404 + no-store，前端拿到后延迟重试（下载完下次重试即命中）
        return JSONResponse({"error": "pending"}, status_code=404,
                            headers={"Cache-Control": "no-store"})

    @r.get("/api/imgcache/status")
    def imgcache_status():
        import gameimg
        return {"ok": True, **gameimg.cache_stats()}

    @r.post("/api/imgcache/clear")
    def imgcache_clear():
        import gameimg
        freed = gameimg.cache_clear()
        return {"ok": True, "freed_bytes": freed}

    return r
