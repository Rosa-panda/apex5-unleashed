# WS 事件总线（ADR-029 B1 自 service.py 抽出，行为零变化）。
# 引擎线程的事件经 publish 线程安全投递到事件循环，WS 端点逐个转发。
# 队列 maxsize=200 与 QueueFull 吞包策略是行为约束，勿改。
import asyncio
import json

from fastapi import WebSocketDisconnect


class WsBus:
    def __init__(self):
        self.clients = set()
        self._loop = {"loop": None}

    def grab_loop(self):
        """startup 时在事件循环线程里抓 loop 引用（原 _grab_loop）。"""
        self._loop["loop"] = asyncio.get_running_loop()

    def publish(self, evt):
        """引擎线程 → 事件循环线程安全投递（原 bus_to_ws，逐字保留）。"""
        loop = self._loop["loop"]
        if loop is None:
            return
        for q in list(self.clients):
            def deliver(q=q):
                try:
                    q.put_nowait(evt)
                except asyncio.QueueFull:
                    pass
            try:
                loop.call_soon_threadsafe(deliver)
            except RuntimeError:
                pass

    async def attach(self, ws, engine):
        """WS 端点主体（原 /ws endpoint 逐字保留）：accept→注册→首帧快照→转发→清理。"""
        await ws.accept()
        q = asyncio.Queue(maxsize=200)
        self.clients.add(q)
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
            self.clients.discard(q)
