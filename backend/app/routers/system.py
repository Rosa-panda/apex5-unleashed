# 系统/基础端点（ADR-029 B2 自 service.py 逐字搬出）：
# favicon/health/ui-error/show/device/state/modes/open-folder
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import protocol


def build_system_router(ctx):
    r = APIRouter()
    engine = ctx.engine

    @r.get("/favicon.ico")
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

    @r.get("/api/health")
    def health():
        return {"ok": True, "mock": engine.force_mock, "online": engine.online}

    class UiErrorReq(BaseModel):
        msg: str = ""
        stack: str = ""
        where: str = ""

    @r.post("/api/ui-error")
    def ui_error(req: UiErrorReq):
        """前端渲染崩溃上报（黑屏诊断）：落 stderr/apex5.log。"""
        import sys
        print(f"[UI-ERROR] {req.where}: {req.msg}\n{req.stack}", file=sys.stderr, flush=True)
        return {"ok": True}

    @r.get("/api/show")
    def show_window():
        """二次启动唤起：新实例探测到本实例后调这里，把已开的窗口拉到前台。"""
        cb = (ctx.ui_hooks or {}).get("show")
        if cb:
            try:
                cb()
            except Exception:
                pass
        return {"ok": True}

    @r.get("/api/device")
    def device():
        return {"kind": engine.dev_kind, "online": engine.online,
                "vid": f"{protocol.VID:04X}", "pid": f"{protocol.PID:04X}"}

    @r.get("/api/state")
    def state():
        return engine.snapshot()

    @r.get("/api/modes")
    def modes():
        return {"trigger": {m: [f[0] for f in s["fields"]] for m, s in protocol.TRIGGER_MODES.items()},
                "grip": [f[0] for f in protocol.GRIP_FIELDS]}

    @r.post("/api/open-folder")
    def open_folder(req: dict = None):
        """打开数据目录（资源管理器）。目录不存在则顺带创建。"""
        import os as _os
        base = _os.environ.get("APPDATA") or _os.path.expanduser("~")
        d = _os.path.join(base, "Apex5Unleashed")
        _os.makedirs(d, exist_ok=True)
        _os.startfile(d)                     # noqa: S606 本机 GUI 行为，路径常量
        return {"ok": True, "path": d}

    return r
