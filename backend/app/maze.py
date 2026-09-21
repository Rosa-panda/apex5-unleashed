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
AUTOCAL_GYRO_QUIET = 30.0   # |陀螺| 低于此 ≈ 静止（raw 量纲，实测平放 ~1）
AUTOCAL_ALPHA = 0.04        # 静止时基线低通收敛系数/帧（~1s 收敛）
# 符号约定（芯片坐标系推导，平放 Z=+1g 已实测）：右倾 → ax 负向变化；
# 前倾（离身） → ay 正向变化。屏幕 x 右正 / y 下正，故 tilt=( -Δax, -Δay )/g。


class MazeService:
    def __init__(self):
        self._lock = threading.Lock()
        self._accel = (0.0, 0.0, 0.0)
        self._gyro = (0.0, 0.0, 0.0)
        self._t = 0.0
        self.frames = 0
        self.rest = None                  # 静止基线 (ax, ay, az)
        self._quiet_frames = 0            # 连续静止帧数（自动校准门）
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
            mag = math.hypot(ax, ay, az)
            # 静止自动校准：手柄放平不动 ~1s，基线自己收敛到位——不再依赖人肉点按钮
            # （真机教训：手动校准点在被拿着/移动的时刻，基线 X 分量高达 1g，
            #  方向颠倒 + 两轴增益不对称都是它导致的，2026-09-21）
            if mag > 2000.0 and math.hypot(*self._gyro) < AUTOCAL_GYRO_QUIET:
                self._quiet_frames += 1
                if self.rest is None:
                    self.rest = self._accel          # 第一批静止样本直接落位
                else:
                    k = AUTOCAL_ALPHA if self._quiet_frames > 30 else 0.2
                    self.rest = tuple(r + k * (a - r) for r, a in zip(self.rest, self._accel))
            else:
                self._quiet_frames = 0
            if mag < 50.0:
                # 加速度计没数据：陀螺仪积分退化模式（dt 真值才有意义）
                dt = (self._t - self._last_t) if self._last_t else 0.0
                self._last_t = self._t
                if 0 < dt < 0.2:
                    gx, gy, _ = self._gyro
                    self._gyro_tilt[0] = (self._gyro_tilt[0] + gy * GYRO_TILT_K * dt * 60) * GYRO_DECAY
                    self._gyro_tilt[1] = (self._gyro_tilt[1] + gx * GYRO_TILT_K * dt * 60) * GYRO_DECAY
            else:
                self._gyro_tilt = [0.0, 0.0]

    # ---------- 手动校准（立即落位；自动校准仍在后台持续微调） ----------
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
                # g 取基线模长：静止时 |a| 恒等于 1g（与姿态无关），静止期抓的基线天然带正确标尺
                tilt = (-(ax - rx) / g, -(ay - ry) / g)
                source = "accel"
            elif mag > 50.0:
                tilt = (0.0, 0.0)
                source = "accel_unchecked"                   # 有数据但还没采到静止基线
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
                "autocal": self._quiet_frames >= 30,
                "has_imu": mag > 50.0 or any(abs(v) > 5 for v in self._gyro),
            }


SERVICE = MazeService()
