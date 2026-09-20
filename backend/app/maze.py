# 体感弹珠迷宫（体验区 #17）：手柄倾斜 → 弹珠滚动的物理倾斜源。
# 数据链：0xEF 帧 → engine._dispatch_motion → MazeService.on_motion。
# 倾斜解算：加速度计重力向量（平放校准取 1g 基准，天然适配任意量程）；
# 若固件不填加速度（模长≈0），退化用陀螺仪积分（带回中衰减，漂但能玩）。
# 这同时也是「我的手柄到底有没有真体感」的答案器：raw 数值 + 模长 + 数据源直接可见。
import math
import threading
import time

GYRO_TILT_K = 0.0025        # 陀螺积分系数（rad/单位·s 量级，手感优先不追物理精确）
GYRO_DECAY = 0.90           # 陀螺模式回中衰减/帧


class MazeService:
    def __init__(self):
        self._lock = threading.Lock()
        self._accel = (0.0, 0.0, 0.0)
        self._gyro = (0.0, 0.0, 0.0)
        self._t = 0.0
        self.frames = 0
        self.rest = None                  # 校准基线 (ax, ay, az)
        self._gyro_tilt = [0.0, 0.0]      # 退化模式的积分倾斜
        self._last_t = 0.0

    # ---------- engine.subscribe_motion 回调 ----------
    def on_motion(self, m):
        with self._lock:
            self._accel = tuple(float(v) for v in m["accel"])
            self._gyro = tuple(float(v) for v in m["gyro"])
            self._t = m["t"]
            self.frames += 1
            ax, ay, az = self._accel
            if math.hypot(ax, ay, az) < 50.0:
                # 加速度计没数据：陀螺仪积分退化模式（dt 真值才有意义）
                dt = (self._t - self._last_t) if self._last_t else 0.0
                self._last_t = self._t
                if 0 < dt < 0.2:
                    gx, gy, _ = self._gyro
                    self._gyro_tilt[0] = (self._gyro_tilt[0] + gy * GYRO_TILT_K * dt * 60) * GYRO_DECAY
                    self._gyro_tilt[1] = (self._gyro_tilt[1] + gx * GYRO_TILT_K * dt * 60) * GYRO_DECAY
            else:
                self._gyro_tilt = [0.0, 0.0]

    # ---------- 校准 ----------
    def calibrate(self):
        with self._lock:
            if math.hypot(*self._accel) < 50.0:
                raise RuntimeError("加速度计无数据，无可校准（见下方原始值诊断）")
            self.rest = self._accel
        return self.status()

    # ---------- 状态 ----------
    def status(self):
        with self._lock:
            ax, ay, az = self._accel
            mag = math.hypot(ax, ay, az)
            if mag > 50.0 and self.rest:
                rx, ry, rz = self.rest
                g = math.hypot(rx, ry, rz) or 1.0
                tilt = ((ax - rx) / g, -(ay - ry) / g)      # 屏幕 y 向下，取负
                source = "accel"
            elif mag > 50.0:
                tilt = (0.0, 0.0)
                source = "accel_unchecked"                   # 有数据但没校准
            else:
                tilt = tuple(self._gyro_tilt)
                source = "gyro_fallback"                     # 固件没填加速度，陀螺积分凑合
            return {
                "tilt": [round(v, 4) for v in tilt],
                "source": source,
                "raw_accel": [round(v, 1) for v in (ax, ay, az)],
                "raw_gyro": [round(v, 1) for v in self._gyro],
                "accel_mag": round(mag, 1),
                "frames": self.frames,
                "rest": list(self.rest) if self.rest else None,
                "has_imu": mag > 50.0 or any(abs(v) > 5 for v in self._gyro),
            }


SERVICE = MazeService()
