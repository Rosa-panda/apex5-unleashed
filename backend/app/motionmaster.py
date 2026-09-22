# 体感中心总闸状态机（ADR-029 B1 自 service.py 抽出，行为零变化；原 ADR-028）。
# 持有：总闸持久化（motion_hub.json）、请求探针计数/落盘日志（motion_api.log）、
# 0xEF 帧→WS 推送（30Hz 节流 + 总闸静默）。时序常量与静默语义是行为约束，勿改。
import time


class MotionMaster:
    def __init__(self, engine, bus, dsu, maze, softmap_hub, raw):
        self.engine = engine
        self.bus = bus
        self.dsu = dsu
        self.maze = maze
        self.softmap_hub = softmap_hub
        self.raw = raw
        # 请求探针：页面 POST 挂死排查（2026-09-21）——GET 到达但 POST 失踪时，
        # 计数器与落盘日志能立刻分辨「请求没到后端」还是「后端处理挂了」。
        self.hits = {"get": 0, "post": 0, "last": "-"}
        self._motion_ws_last = {"t": 0.0}

        # ---- 总闸状态持久化，上次开着本次启动自动恢复（原 791-829 行序逐字） ----
        # 总闸真相源 = 持久态本身（不再借用 engine.raw_motion——raw 位图流是拓展键/宏的
        # 基础设施按需开关，见 rawstream.py；总闸只管「体感消费者」）
        self.hub = {"master": self._load()}
        raw.demands["master"] = self.hub["master"]
        if self.hub["master"]:
            try:
                dsu.start()                    # 上次开着 → DSU 桥自动回来
            except Exception:
                pass
            if engine.online:                  # 设备已先于本接线接入的场景：补开流
                raw.eval("master-restore")

        # 流状态对账看门狗：宏/档案写入的 enable_raw_stream 保险、任何别处强开的流，
        # 30s 内被纠正回需求决策（无人消费即关，手柄恢复可休眠）
        raw.start_watchdog()

        # 订阅保持原位序：在 maze/dsu 之后、softmap/diag 之前（0xEF 帧分发顺序敏感）
        engine.subscribe_motion(self.to_ws)

    # ---- 持久化 ----
    @staticmethod
    def _file():
        import os as _os
        return _os.path.join(_os.environ.get("APPDATA", "."), "Apex5Unleashed", "motion_hub.json")

    def _load(self):
        import json as _json
        try:
            with open(self._file(), "r", encoding="utf-8") as f:
                return bool(_json.load(f).get("master"))
        except (OSError, ValueError):
            return False

    def save(self, v):
        import json as _json
        import os as _os
        p = self._file()
        _os.makedirs(_os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump({"master": bool(v)}, f)
        _os.replace(tmp, p)

    # ---- 探针日志 ----
    def log(self, msg):
        import os as _os
        self.hits["last"] = msg
        try:
            base = _os.path.join(_os.environ.get("APPDATA", "."), "Apex5Unleashed")
            _os.makedirs(base, exist_ok=True)
            with open(_os.path.join(base, "motion_api.log"), "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        except Exception:
            pass

    # ---- 聚合状态 ----
    def status(self, note=None):
        return {"ok": True, "master": self.hub["master"],
                "raw": bool(self.engine.raw_motion), "note": note,
                "dsu": self.dsu.status(),
                "gyro": {"enabled": bool(self.softmap_hub.gyro.cfg.get("enabled"))},
                "ui_get": self.hits["get"], "ui_post": self.hits["post"],
                "ui_last": self.hits["last"]}

    # ---- 0xEF 帧 → WS 推送（ADR-028 补丁：替代前端 40ms HTTP 轮询） ----
    # 0xEF 流 ~370Hz 全在 HID 线程，HTTP 轮询 25Hz 延迟高且挤占请求队列——弹珠「半天动
    # 一下」的根因。改为 WS 推 tilt：30Hz 节流（体感 UI 足够顺滑），走 bus 线程安全
    # 投递，不进 events 历史（不撑爆事件流，不触发前端重渲染）。总闸关闭时推
    # 送静默（试玩场/体感 UI 冻结），但流本身仍在跑——拓展键直读/宏录制还靠它。
    def to_ws(self, _m):
        if not self.hub["master"]:    # 总闸关闭 → 体感 UI 静默（流本身仍在跑，喂拓展键/宏）
            return
        n = time.monotonic()
        if n - self._motion_ws_last["t"] < 1 / 30:
            return
        self._motion_ws_last["t"] = n
        st = self.maze.status()
        self.bus.publish({"ts": "", "kind": "motion", "tilt": st["tilt"],
                          "source": st["source"], "frames": st["frames"],
                          "has_imu": st["has_imu"], "autocal": st["autocal"],
                          "anchor": st["anchor"]})
