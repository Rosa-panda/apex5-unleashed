# 屏幕端点（ADR-029 B4 自 service.py 逐字搬出；原 ADR-018 R4 二期）。
# 红线：真机烧写必须 confirm=true 且用户知情。
from fastapi import APIRouter
from pydantic import BaseModel

import screenpack

from .common import err


def build_screen_router(ctx):
    r = APIRouter()
    engine = ctx.engine
    _screen_pending = {"frames": None, "interval": 100, "name": "", "seconds": 0}

    class ScreenConvertReq(BaseModel):
        data_b64: str                   # GIF/图片文件内容 base64
        name: str = ""
        mode: str = "fill"              # fill/fit/stretch
        target_frames: int = 30         # 等距抽帧目标（0=不抽帧）

    @r.post("/api/screen/convert")
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

    @r.get("/api/screen/status")
    def screen_status():
        return engine.last_screen_event

    @r.get("/api/screen/flags")
    def screen_flags():
        try:
            return {"ok": True, **engine.screen_get_flags()}
        except Exception as e:
            return err(e)

    class ScreenFlagReq(BaseModel):
        on: bool

    @r.post("/api/screen/animation")
    def screen_animation(req: ScreenFlagReq):
        try:
            engine.screen_set_flag(9, req.on)       # 19/9 动画常亮（息屏显示）
            return {"ok": True, **engine.screen_get_flags()}
        except Exception as e:
            return err(e)

    @r.post("/api/screen/statusbar")
    def screen_statusbar(req: ScreenFlagReq):
        try:
            engine.screen_set_flag(8, req.on)       # 19/8 状态栏常亮
            return {"ok": True, **engine.screen_get_flags()}
        except Exception as e:
            return err(e)

    @r.post("/api/screen/flash")
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

    return r
