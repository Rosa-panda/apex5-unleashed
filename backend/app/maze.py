# 体感弹珠迷宫（体验区 #17）：手柄倾斜 → 弹珠滚动的物理倾斜源。
# 数据链：0xEF 帧 → engine._dispatch_motion → MazeService.on_motion。
#
# 姿态解算 v2（2026-09-21 深度逆向后的结论落地）：
#   v1 用加速度计裸倾角（重力向量/基线），静止完美、一动就废——线加速度污染重力，
#   这就是「死路」的根源。主机（Switch/PS5）靠出厂 NVM 标定 + 在线归零解决；
#   出厂标定本质只是「每轴零偏+增益」一组常量，公开渠道拿不到（openflydigi 硬编码
#   4096/g、内核 xpad 不碰 IMU、DS5 模拟层标定抄自真索尼），但可以在线估计——
#   而且估计值随温漂更新，比烧死在 NVM 里的更准。
#   v2 = 互补滤波融合：陀螺积分扛高频 + 加速度重力向量纠低频漂移，
#   附带陀螺零偏自动跟踪（静止低通收敛）。纯加速度计 v1 保留为融合失败退化路径。
import math
import threading

# 互补滤波参数
COMP_ALPHA = 0.03           # 加速度权重/帧（~300Hz → 时间常数 ~0.11s）
GYRO_DPS_PER_LSB = 0.05     # 陀螺量纲假设（openflydigi 同款，未实测校准，可调）
DEG2G = math.pi / 180.0     # 小角度下 tilt(g 单位) ≈ 角度(rad)
DT_MAX = 0.05               # dt 钳制：运动流断流后回来的第一帧不许跳变
AUTOCAL_GYRO_QUIET = 30.0   # |陀螺| 低于此 ≈ 静止（raw 量纲，实测平放 ~1）
ANCHOR_CAPTURE_FRAMES = 40  # 平放静止连续 ~0.15s 即采锚（一次采准，之后冻结）
BIAS_ALPHA = 0.05           # 陀螺零偏低通系数/帧（静止期跟踪，姿态无关、用户无感）
FLAT_Z_RATIO = 0.7          # 平放判定：|az|/mag 超过它 ≈ 平放（锚点只在此姿态采）
# 符号约定（芯片坐标系推导，平放 Z=+1g 已实测；2026-09-21 真机校准：y 轴默认
# 反了——用户实测前倾球应向下滚，故 tilt_y 取 +Δay / -gx）：右倾 → ax 负向变化；
# 前倾（离身） → ay 正向变化。屏幕 x 右正 / y 下正，故 tilt=( -Δax, +Δay )/g；
# 陀螺积分沿用 v1 退化模式实测映射：tilt_x ← gy、tilt_y ← -gx。


class MazeService:
    def __init__(self):
        self._lock = threading.Lock()
        self._accel = (0.0, 0.0, 0.0)
        self._gyro = (0.0, 0.0, 0.0)
        self._t = 0.0
        self.frames = 0
        self.rest = None                  # 静止基线 (ax, ay, az)——重力零偏
        self.gyro_bias = None             # 陀螺零偏 (gx, gy, gz)——静止低通跟踪
        self._quiet_frames = 0            # 连续静止帧数（自动校准门）
        self._tilt = [0.0, 0.0]           # 融合倾斜输出（g 单位小角近似）
        self._last_t = 0.0
        self._mode = "boot"               # boot / fusion / accel / gyro_fallback
        self._anchor = "boot"             # flat=平放收敛锚点 / held=非平放保持 / moving=运动中

    # ---------- engine.subscribe_motion 回调 ----------
    def on_motion(self, m):
        with self._lock:
            self._accel = tuple(float(v) for v in m["accel"])
            self._gyro = tuple(float(v) for v in m["gyro"])
            self._t = m["t"]
            self.frames += 1
            ax, ay, az = self._accel
            mag = math.hypot(ax, ay, az)
            quiet = mag > 2000.0 and math.hypot(*self._gyro) < AUTOCAL_GYRO_QUIET
            # 平放判定：重力主要沿 +Z。
            # 真机教训（用户实测两轮）：锚点自动刷新=「竖放一会儿变新平地」，
            # 使用中偷换锚点更是错——校准是采一次就焊死的动作，不是持续过程。
            flat = az > FLAT_Z_RATIO * mag

            if quiet:
                self._quiet_frames += 1
                # 重力锚点：平放静止一次性采集（采够帧数落位），之后冻结。
                # 只有「立即校准」按钮才重设——锚点是用户锚定的，软件不替用户改。
                if flat and self.rest is None:
                    if self._quiet_frames >= ANCHOR_CAPTURE_FRAMES:
                        self.rest = self._accel
                # 陀螺零偏：任何静止姿态持续跟踪（与姿态无关、不影响「哪里是平」，
                # 只让融合不漂——这不是校准，用户无感）
                if self.gyro_bias is None:
                    self.gyro_bias = self._gyro
                else:
                    self.gyro_bias = tuple(b + BIAS_ALPHA * (g - b)
                                           for b, g in zip(self.gyro_bias, self._gyro))
            else:
                self._quiet_frames = 0
            self._anchor = ("flat" if flat else "held") if quiet else "moving"

            dt = min(max(self._t - self._last_t, 0.0), DT_MAX) if self._last_t else 0.0
            self._last_t = self._t

            if mag > 2000.0 and self.rest:
                # ---- 主路径：互补滤波融合，绝对重力角 ----
                # 倾角 = 重力水平分量/1g = sin(倾角)：平放 0、竖直 ±1（90°），
                # 与「当前姿态」无关；rest 只扣安装面小偏差（ax/ay 各 <0.1g）。
                rx, ry, _ = self.rest
                accel_tilt = (-(ax - rx) / mag, (ay - ry) / mag)
                bias = self.gyro_bias or (0.0, 0.0, 0.0)
                gx = self._gyro[0] - bias[0]
                gy = self._gyro[1] - bias[1]
                rate = GYRO_DPS_PER_LSB * DEG2G          # raw·s → rad(g 单位)
                if quiet:
                    # 静止：直接收敛到重力向量，陀螺积分清零防漂
                    w = 1.0
                else:
                    w = COMP_ALPHA
                for i, (gyro_term, a_t) in enumerate(
                        ((gy * rate, accel_tilt[0]), (-gx * rate, accel_tilt[1]))):
                    pred = self._tilt[i] + gyro_term * dt
                    self._tilt[i] = a_t * w + pred * (1.0 - w)
                self._mode = "fusion"
            elif mag > 50.0:
                # 有加速度但还没采到静止基线：裸倾角（无基准，先回零）
                self._tilt = [0.0, 0.0]
                self._mode = "accel_unchecked"
            else:
                # 加速度计没数据：陀螺积分退化模式（去零偏 + 回中衰减）
                if 0 < dt < 0.2:
                    bias = self.gyro_bias or (0.0, 0.0, 0.0)
                    gy = self._gyro[1] - bias[1]
                    gx = self._gyro[0] - bias[0]
                    rate = GYRO_DPS_PER_LSB * DEG2G
                    self._tilt[0] = (self._tilt[0] + gy * rate * dt) * 0.90
                    self._tilt[1] = (self._tilt[1] - gx * rate * dt) * 0.90
                self._mode = "gyro_fallback"

    # ---------- 手动校准（立即落位；自动校准仍在后台持续微调） ----------
    def calibrate(self):
        with self._lock:
            if math.hypot(*self._accel) < 50.0:
                raise RuntimeError("加速度计无数据，无可校准（见下方原始值诊断）")
            self.rest = self._accel
            self.gyro_bias = self._gyro
            self._tilt = [0.0, 0.0]
            self._quiet_frames = 0
        return self.status()

    # ---------- 状态 ----------
    def status(self):
        with self._lock:
            ax, ay, az = self._accel
            mag = math.hypot(ax, ay, az)
            tilt = self._tilt
            return {
                "tilt": [round(max(-1.5, min(1.5, v)), 4) for v in tilt],
                "source": self._mode,
                "raw_accel": [round(v, 1) for v in (ax, ay, az)],
                "raw_gyro": [round(v, 1) for v in self._gyro],
                "accel_mag": round(mag, 1),
                "frames": self.frames,
                "rest": list(self.rest) if self.rest else None,
                "gyro_bias": [round(v, 2) for v in self.gyro_bias] if self.gyro_bias else None,
                "anchor": self._anchor,
                "anchor_locked": self.rest is not None,
                "autocal": self.rest is not None,
                "has_imu": mag > 50.0 or any(abs(v) > 5 for v in self._gyro),
            }


SERVICE = MazeService()
