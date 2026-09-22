# 控制端点（ADR-029 B3 自 service.py 逐字搬出）：
# trigger/clear, rumble, grip/unbind, panic, proxy/reclaim
from fastapi import APIRouter
from pydantic import BaseModel

from .common import err


def build_control_router(ctx):
    r = APIRouter()
    engine = ctx.engine

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

    @r.post("/api/trigger")
    def trigger(req: TriggerReq):
        try:
            engine.set_trigger(req.side, req.mode, req.params,
                               preview=not req.apply, source="ui")
            return {"ok": True}
        except Exception as e:
            return err(e)

    @r.post("/api/trigger/clear")
    def trigger_clear(req: TriggerReq):
        try:
            for s in (["left", "right"] if req.side == "both" else [req.side]):
                engine.clear_trigger(s, source="ui")
            return {"ok": True}
        except Exception as e:
            return err(e)

    @r.post("/api/rumble")
    def rumble(req: RumbleReq):
        try:
            engine.set_rumble(req.l, req.r, req.duration, source="ui")
            return {"ok": True}
        except Exception as e:
            return err(e)

    @r.post("/api/grip")
    def grip(req: GripReq):
        try:
            engine.bind_grip(req.side, req.params, source="ui")
            return {"ok": True}
        except Exception as e:
            return err(e)

    @r.post("/api/grip/unbind")
    def grip_unbind(req: GripReq):
        try:
            for s in (["left", "right"] if req.side == "both" else [req.side]):
                engine.unbind_grip(s, source="ui")
            return {"ok": True}
        except Exception as e:
            return err(e)

    @r.post("/api/panic")
    def panic():
        engine.panic(source="ui")
        return {"ok": True}

    @r.post("/api/proxy/reclaim")
    def proxy_reclaim():
        engine.reclaim()
        return {"ok": True}

    return r
