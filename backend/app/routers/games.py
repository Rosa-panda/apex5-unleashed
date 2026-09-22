# 游戏档案端点（ADR-029 B5 自 service.py 逐字搬出；原 ADR-014/017）
from fastapi import APIRouter
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
        preset_id: str = ""
        note: str = ""

    class LinkReq(BaseModel):
        preset_id: str = ""

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
        try:
            return {"ok": True, "game": games.save(req.model_dump())}
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
        return {"available": bool(officialimport.official_path()),
                "path": officialimport.official_path() or officialimport.OFFICIAL_JSON}

    class UniversalVibReq(BaseModel):
        enabled: bool

    @r.post("/api/vib/universal")
    def vib_universal(req: UniversalVibReq):
        """通用震动联动：游戏震动→扳机反馈（设备端固件路由，任何游戏生效）。"""
        try:
            return {"ok": True, "universal_vib": games.set_universal_vib(req.enabled, engine)}
        except Exception as e:
            return err(e)

    @r.post("/api/games/{gid}/link")
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
