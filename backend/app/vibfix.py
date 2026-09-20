# 游戏震动修复（2026-09-20 原神案例）：飞智空间站的虚拟手柄驱动会抢走 XInput
# 0 号槽——原神这类只给 0 号槽发震动的游戏，震动全进虚拟手柄；空间站服务停用后
# 转发链断，真手柄永远收不到（输入不受影响 →「能玩、不震」）。
# 本模块提供状态检测 + 一键禁用/启用（ShellExecute runas 弹 UAC），
# 替代"天天动设备管理器"（用户原话：很离谱）。
# 恢复场景：想用空间站键鼠映射/陀螺仪时再启用。
import ctypes

# 飞智公司英文名就是 GeniTech（Flydigi 是品牌名），别被名字骗了——这是飞智自家的
INSTANCE_ID = "ROOT\\GENITECH_VIRTUAL_GAMEPAD_DEVICE\\0000"
SERVICE = "hidvirtualdriver"

_DN_HAS_PROBLEM = 0x400
_CM_PROB_DISABLED = 0x16


def status():
    """absent=没装 / disabled=已禁用（震动修复态）/ enabled=活跃（会抢 0 号槽）。"""
    cfg = ctypes.windll.CfgMgr32
    devinst = ctypes.c_ulong()
    if cfg.CM_Locate_DevNodeW(ctypes.byref(devinst), INSTANCE_ID, 0) != 0:
        return "absent"
    st = ctypes.c_ulong()
    prob = ctypes.c_ulong()
    # CM_Get_DevNode_Status(pulStatus, pulProblemNumber, devinst, flags)
    if cfg.CM_Get_DevNode_Status(ctypes.byref(st), ctypes.byref(prob), devinst, 0) != 0:
        return "absent"
    if (st.value & _DN_HAS_PROBLEM) and prob.value == _CM_PROB_DISABLED:
        return "disabled"
    return "enabled"


def set_enabled(enabled):
    """弹 UAC 提权执行设备禁用/启用。返回 True=UAC 已发起（用户点了「是」）。
    是否真正生效由前端轮询 status() 确认（设备树变更异步）。"""
    verb = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
    ps = f'-NoProfile -Command "{verb} -InstanceId \'{INSTANCE_ID}\' -Confirm:$false"'
    # SW_HIDE=0：powershell 窗口藏起来，只露 UAC 授权框
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", ps, None, 0)
    return r > 32                       # <=32 = SE_ERR_*（用户点了「否」= 5）


# ---- 自动修复（检测到才动）：会话级提权限频。用户点了「否」就别每次进游戏都弹 UAC。 ----
_auto_attempts = 0
_AUTO_MAX = 3


def auto_fix_allowed():
    return _auto_attempts < _AUTO_MAX


def auto_disable():
    """自动修复专用入口：发一次提权禁用并记一次数。"""
    global _auto_attempts
    _auto_attempts += 1
    return set_enabled(False)
