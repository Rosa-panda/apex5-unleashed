# 体验区（Experience Lab，ADR-026）：功能挖掘 16 项的统一孵化区。
# 注册表是功能清单的唯一真相源（前端只渲染不硬编码）；判定存
# %APPDATA%\Apex5Unleashed\exp_verdicts.json，是「哪些功能值得转正」的证据链。
# 企划书：《APEX5-功能挖掘-企划书.md》（工作区根目录），feature.plan 指向其 §三 节号。
import json
import os
import time

# 梯队：1=核心玩法 2=生态/管理 3=补全/实验
TIER_LABEL = {1: "第一梯队", 2: "第二梯队", 3: "第三梯队"}

FEATURES = [
    {"id": "gyro", "tier": 1, "plan": "#1", "title": "体感瞄准（软件层）",
     "desc": "陀螺仪转鼠标，全游戏体感瞄准。三态开关（关/按住激活/常开），官方算法参数起步。",
     "enabled": True},
    {"id": "turbo", "tier": 1, "plan": "#2", "title": "连发 Turbo",
     "desc": "任意键固件级连发（按住=连点），零软件开销，关软件照样生效。",
     "enabled": True},
    {"id": "stickcfg", "tier": 1, "plan": "#3", "title": "曲线编辑器",
     "desc": "摇杆响应曲线/死区/圆率 + 扳机行程曲线可视化编辑。",
     "enabled": True},
    {"id": "devcfg", "tier": 1, "plan": "#4", "title": "设备设置页",
     "desc": "回报率/摇杆精度/灵敏度/睡眠/昵称/档案名/cmd48 七模块版本，一个页面收拢。",
     "enabled": True},
    {"id": "arbitration", "tier": 1, "plan": "#5", "title": "共存仲裁升级",
     "desc": "代理权从抓包推断升级为设备实名（cmd28/cmd16 control_by），侧栏显示当前主人。",
     "enabled": True},
    {"id": "gyrofw", "tier": 1, "plan": "#6", "title": "体感映射（固件层）",
     "desc": "blob motion 块固件直通：陀螺→摇杆，零延迟、无软件依赖。与软件层互斥。",
     "enabled": True},
    {"id": "stickmap", "tier": 2, "plan": "#7", "title": "摇杆→鼠标/键盘",
     "desc": "左/右摇杆整体映射成鼠标或键盘方向键（无原生支持游戏的兜底、HTPC 场景）。",
     "enabled": True},
    {"id": "rgbbridge", "tier": 2, "plan": "#8", "title": "Mod 灯效桥",
     "desc": "7878 的 RGBUpdate/PlayerLED 指令翻译成手柄灯光——官方静默丢弃的部分。",
     "enabled": True},
    {"id": "diagnostics", "tier": 2, "plan": "#9", "title": "摇杆体检与校准",
     "desc": "实时散点图 + 画圆误差报告 + 一键 ADC 校准 + 回报率实测。",
     "enabled": True},
    {"id": "slots", "tier": 2, "plan": "#10", "title": "4 配置槽快切",
     "desc": "四套板载配置管理 + fn+A/B/X/Y 手柄端快切开关。",
     "enabled": True},
    {"id": "sharecode", "tier": 2, "plan": "#11", "title": "配置分享码",
     "desc": "预设/档案/宏导出为分享码字符串，社区流通（无云端，纯本地编解码）。",
     "enabled": True},
    {"id": "switchbank", "tier": 2, "plan": "#12", "title": "Switch 第二银行",
     "desc": "PC 上配置 Switch 档案（槽 4-7，cmd171 写入），Switch 下生效。",
     "enabled": True},
    {"id": "gripvib", "tier": 3, "plan": "#13", "title": "握把震动调校",
     "desc": "每侧 Min/Max/Scale 曲线 + 「Xbox 感」预设（50%）+ GripSync 震动同步灯效。",
     "enabled": True},
    {"id": "screenplus", "tier": 3, "plan": "#14", "title": "屏幕补全",
     "desc": "状态栏常亮开关 + GIF 帧范围裁剪 + 恢复出厂动画。",
     "enabled": True},
    {"id": "factoryreset", "tier": 3, "plan": "#15", "title": "危险区：重置",
     "desc": "重置全部配置档案（cmd175）。双确认 + 全量备份先行。全企划最危险项。",
     "enabled": True},
]

VERDICT_LABEL = {"good": "👍 好用", "bad": "👎 不好用", "pending": "⏸ 待测"}


class Verdicts:
    """判定账本：{feature_id: {verdict, note, ts}}。损坏/缺失一律按空账本起。"""

    def __init__(self, appdata=None):
        base = appdata or os.path.join(os.environ.get("APPDATA", "."), "Apex5Unleashed")
        os.makedirs(base, exist_ok=True)
        self.path = os.path.join(base, "exp_verdicts.json")
        self.data = {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data = loaded
        except (OSError, ValueError):
            pass

    def get(self, fid):
        return self.data.get(fid, {})

    def set(self, fid, verdict, note=""):
        if verdict not in ("good", "bad", "pending"):
            raise ValueError(f"bad verdict: {verdict}")
        self.data[fid] = {"verdict": verdict, "note": note, "ts": int(time.time())}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)
        return self.data[fid]

    def summary(self):
        n = {"good": 0, "bad": 0, "pending": 0}
        for fid, v in self.data.items():
            if isinstance(v, dict) and v.get("verdict") in n:
                n[v["verdict"]] += 1
        return n
