# WS 事件流端点（ADR-029 B2）：主体在 wsbus.WsBus.attach（逐字保留）。
from fastapi import APIRouter, WebSocket


def build_ws_router(ctx):
    r = APIRouter()

    @r.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ctx.bus.attach(ws, ctx.engine)

    return r
