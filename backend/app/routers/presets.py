# 预设端点（ADR-029 B5 自 service.py 逐字搬出）
from fastapi import APIRouter
from pydantic import BaseModel

from .common import err


def build_presets_router(ctx):
    r = APIRouter()
    store = ctx.store
    engine = ctx.engine

    class PresetReq(BaseModel):
        name: str
        note: str = ""
        actions: list = []

    @r.get("/api/presets")
    def presets_list():
        return store.list()

    @r.post("/api/presets")
    def presets_save(req: PresetReq):
        try:
            return {"ok": True, "preset": store.save(req.model_dump())}
        except Exception as e:
            return err(e)

    @r.post("/api/presets/{pid}/apply")
    def presets_apply(pid: str):
        try:
            return {"ok": True, "result": store.apply(pid, engine)}
        except Exception as e:
            return err(e)

    @r.delete("/api/presets/{pid}")
    def presets_delete(pid: str):
        try:
            store.delete(pid)
            return {"ok": True}
        except Exception as e:
            return err(e)

    return r
