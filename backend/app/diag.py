# 摇杆诊断（ADR-027，体验区 #9）：0xEF 运动分发采样 + ADC 校准 + 自动校准开关。
# cmd240 ADC 校准（RESEARCH §C：payload [1]=开始 [2]=结束）细节真机未验，UI 标注。
import time

import protocol


class StickSampler:
    """订阅运动分发，环形缓冲摇杆原始值。start(seconds) 后的样本才算数。"""

    MAX = 60 * 400                       # ~1 分钟 @370Hz 上限

    def __init__(self):
        self.samples = []
        self.since = None                # 开始采样的 monotonic 时刻；None = 不采

    def on_motion(self, m):
        if self.since is None:
            return
        self.samples.append((m["t"], m["lx"], m["ly"], m["rx"], m["ry"]))
        if len(self.samples) > self.MAX:
            self.samples = self.samples[-self.MAX // 2:]

    def start(self, seconds):
        self.since = time.monotonic()
        self.until = self.since + seconds
        self.samples = []
        return {"ok": True, "seconds": seconds}

    def data(self):
        """返回采样统计 + 降采样散点（前端画图用）。"""
        if self.since is None:
            return {"running": False}
        running = time.monotonic() < self.until
        s = self.samples
        out = {"running": running, "n": len(s)}
        if s:
            for name, ix, iy in (("left", 1, 2), ("right", 3, 4)):
                xs, ys = [p[ix] for p in s], [p[iy] for p in s]
                out[name] = {"min_x": min(xs), "max_x": max(xs),
                             "min_y": min(ys), "max_y": max(ys),
                             "center_x": sum(xs) / len(xs), "center_y": sum(ys) / len(ys)}
            step = max(1, len(s) // 1200)
            out["points"] = [[p[1], p[2], p[3], p[4]] for p in s[::step]]
            span = s[-1][0] - s[0][0]
            out["rate_hz"] = round(len(s) / span, 1) if span > 0 else None
        if not running:
            self.since = None
        return out


class Diagnostics:
    def __init__(self, engine):
        self.engine = engine
        self.sampler = StickSampler()

    def on_motion(self, m):
        self.sampler.on_motion(m)

    def sample(self, seconds):
        if not self.engine.online:
            raise RuntimeError("设备不在线")
        return self.sampler.start(seconds)

    def adc_calib(self, stage):
        """cmd240：stage 'start'|'stop'。校准期间不要碰摇杆（RESEARCH 推断，UI 标注待验）。"""
        if not self.engine.online:
            raise RuntimeError("设备不在线")
        payload = bytes([1 if stage == "start" else 2])
        self.engine.send_checked(protocol.build_crc(240, payload), 240, source="diag")
        return {"ok": True, "stage": stage}

    def autocal(self, on):
        """自动校准开关 = cmd19 sub6（bit5）。"""
        self.engine.send_checked(
            protocol.build(protocol.CMD_SETTING, bytes([6, 1 if on else 0])),
            protocol.CMD_SETTING, source="diag")
        return {"ok": True, "autocal": on}
