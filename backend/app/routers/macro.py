# 宏端点（ADR-029 B4 自 service.py 逐字搬出；原 ADR-021：板载宏，触发键限六拓展键）。
# 录制 start/stop 走 ctx.raw 需求登记表（ADR-028 修订 2）。
from fastapi import APIRouter
from pydantic import BaseModel

from .common import err


def build_macro_router(ctx):
    r = APIRouter()
    # ctx.raw 由 AppContext.build() 构造（ADR-029 B7）；端点内经 ctx 取——
    # 服务群组装与 router include 的先后由 service.create_app 保证，router 不做假设

    @r.get("/api/macro/config")
    def macro_config():
        import macro
        try:
            return macro.MANAGER.read()
        except Exception as e:
            return err(e)

    class MacroWriteReq(BaseModel):
        macros: list = []               # [{key_id, type, interval, name, actions:[{t,key,ev}]}]
        unbind: list = []               # 需要还原透传（255）的拓展键名

    @r.post("/api/macro/write")
    def macro_write(req: MacroWriteReq):
        import macro
        try:
            # 宏页与触发键绑定同在 profile blob，一次提交（v3.1 方案，ADR-021 修订）
            return macro.MANAGER.write(req.macros, unbind=req.unbind)
        except Exception as e:
            return err(e)

    @r.post("/api/macro/record/start")
    def macro_record_start():
        import macro
        ctx.raw.demands["macro"] = True     # 录制要吃 0xEF 位图流 → 登记需求开流
        ctx.raw.eval("macro-rec")
        macro.RECORDER.start()
        return {"ok": True}

    @r.post("/api/macro/record/stop")
    def macro_record_stop():
        import macro
        ctx.raw.demands["macro"] = False    # 撤需求；流是否关由 raw.eval 按其余消费者决
        ctx.raw.eval("macro-rec-end")
        return {"ok": True, **macro.RECORDER.stop()}

    @r.get("/api/macro/record/status")
    def macro_record_status():
        import macro
        return macro.RECORDER.status()

    @r.post("/api/macro/backup")
    def macro_backup():
        import macro
        try:
            return {"ok": True, **macro.MANAGER.backup()}
        except Exception as e:
            return err(e)

    @r.post("/api/macro/restore")
    def macro_restore():
        import macro
        try:
            return macro.MANAGER.restore()
        except Exception as e:
            return err(e)

    return r
