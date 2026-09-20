# 游戏震动修复（2026-09-20 原神案例）：飞智空间站的虚拟手柄驱动会抢走 XInput
# 0 号槽——原神这类只给 0 号槽发震动的游戏，震动全进虚拟手柄；空间站服务停用后
# 转发链断，真手柄永远收不到（输入不受影响 →「能玩、不震」）。
#
# 出手语义（防"无头案"设计，用户红线：不留查不到根源的永久改动）：
#   临时修复 = 默认。提权脚本自带哨兵：禁用设备后盯着本软件进程，进程一退出
#              立刻 Enable 恢复原状——崩溃/被杀也覆盖（哨兵只认进程死活）。
#              重启/注销哨兵死了留下残留 → needs_selfheal() 下次启动自愈。
#   永久修复 = 仅用户在设置页显式点「永久修复」才持久，账本留痕。
#   每次出手都写 %APPDATA%\Apex5Unleashed\vibfix.json（时间/方向/模式），
#   任何"谁动了我的设备"的疑问都能从账本+设置页卡片直接找到答案。
import ctypes
import json
import os
import time

# 飞智公司英文名就是 GeniTech（Flydigi 是品牌名），别被名字骗了——这是飞智自家的
INSTANCE_ID = "ROOT\\GENITECH_VIRTUAL_GAMEPAD_DEVICE\\0000"
SERVICE = "hidvirtualdriver"

_DN_HAS_PROBLEM = 0x400
_CM_PROB_DISABLED = 0x16


def status():
    """absent=没装 / disabled=已禁用 / enabled=活跃（会抢 0 号槽）。"""
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


def _elevate(ps_script):
    """UAC 提权跑一段 PowerShell（窗口藏起来，只露授权框）。
    返回 True=授权通过（UAC 点了「是」）；设备树变更异步，由前端轮询确认。"""
    r = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", "powershell.exe", f'-NoProfile -Command "{ps_script}"', None, 0)
    return r > 32                       # <=32 = SE_ERR_*（用户点了「否」= 5）


def fix_temporary():
    """临时修复：禁用 + 哨兵。哨兵 = 提权脚本里的等待循环，本软件进程一死
    就 Enable 还原。一次 UAC 全包（禁用+恢复），退出无需再弹授权。"""
    pid = os.getpid()
    ok = _elevate(
        f"Disable-PnpDevice -InstanceId '{INSTANCE_ID}' -Confirm:$false; "
        f"while (Get-Process -Id {pid} -ErrorAction SilentlyContinue) "
        f"{{ Start-Sleep 5 }}; "
        f"Enable-PnpDevice -InstanceId '{INSTANCE_ID}' -Confirm:$false")
    if ok:
        ledger_record("temporary", "disabled")
    return ok


def fix_permanent():
    """永久修复：仅显式点击，禁用跨重启持久（账本留痕，恢复随时一键）。"""
    ok = _elevate(f"Disable-PnpDevice -InstanceId '{INSTANCE_ID}' -Confirm:$false")
    if ok:
        ledger_record("permanent", "disabled")
    return ok


def restore():
    """恢复虚拟手柄（手动恢复 / 自愈残留共用）。"""
    ok = _elevate(f"Enable-PnpDevice -InstanceId '{INSTANCE_ID}' -Confirm:$false")
    if ok:
        ledger_record("restore", "enabled")
    return ok


def needs_selfheal():
    """启动自检：上次会话是临时修复且设备仍处禁用 = 异常退出/重启留下的残留，
    系统状态和用户预期（原始状态）不一致，应自动恢复。永久修复不算残留。"""
    d = ledger_get()
    return d.get("mode") == "temporary" and d.get("state") == "disabled" \
        and status() == "disabled"


# ---- 自动修复（检测到才动）：会话级提权限频。用户点了「否」就别每次进游戏都弹 UAC。 ----
_auto_attempts = 0
_AUTO_MAX = 3


def auto_fix_allowed():
    return _auto_attempts < _AUTO_MAX


def auto_disable():
    """自动修复专用入口：临时修复 + 记一次数。"""
    global _auto_attempts
    _auto_attempts += 1
    return fix_temporary()


# ---- 出手账本：任何禁用/恢复都留痕，防"查不到根源" ----
def _ledger_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Apex5Unleashed", "vibfix.json")


def ledger_get():
    try:
        with open(_ledger_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"mode": None, "state": None, "since": None, "history": []}


def ledger_record(action, state):
    d = ledger_get()
    now = time.strftime("%Y-%m-%d %H:%M")
    d["mode"] = action if state == "disabled" else None   # 恢复后不再处于任何修复模式
    d["state"] = state
    d["since"] = now
    d.setdefault("history", [])
    d["history"].insert(0, {"ts": now, "action": action, "state": state})
    d["history"] = d["history"][:20]                      # 只留最近 20 条
    try:
        os.makedirs(os.path.dirname(_ledger_path()), exist_ok=True)
        with open(_ledger_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
