# 托盘（线程T）：3 态图标 + 菜单。图形统一走 icon.py 的自绘手柄（与窗口图标同源）。
import threading

import icon


def _icon_png(status):
    return icon.pad_image(status, 64)


ICONS = {
    "self": _icon_png("self"),        # 正常：青手柄
    "external": _icon_png("external"),  # 被接管：橙手柄
    "offline": _icon_png("offline"),    # 无设备：灰手柄
}

TIPS = {"self": "Apex5 Unleashed — 代理中", "external": "Apex5 Unleashed — 已被外部接管",
        "offline": "Apex5 Unleashed — 未连接手柄"}


class Tray:
    def __init__(self, engine, on_show, on_quit):
        self.engine = engine
        self._status = "offline"
        self.icon = None
        self._on_show = on_show
        self._on_quit = on_quit

    def start(self):
        import pystray
        menu = pystray.Menu(
            pystray.MenuItem("显示主窗口", self._show, default=True),
            pystray.MenuItem("紧急复位 (Panic)", self._panic),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._quit),
        )
        self.icon = pystray.Icon("Apex5Unleashed", ICONS[self._status], TIPS[self._status], menu)
        self.engine.subscribe(self._on_evt)
        threading.Thread(target=self.icon.run, daemon=True, name="tray").start()

    def _show(self, *_):
        if self._on_show:
            self._on_show()

    def notify_minimized(self):
        """窗口 X 首次隐藏时告知去向（只弹一次，别烦人）。"""
        if not self.icon:
            return
        try:
            self.icon.notify("已最小化到托盘——双击角标图标恢复窗口，右键可选择完全退出",
                             "Apex5 Unleashed")
        except Exception:
            pass

    def _panic(self, *_):
        self.engine.panic(source="tray")

    def _quit(self, *_):
        if self._on_quit:
            self._on_quit()
        if self.icon:
            self.icon.stop()

    def _on_evt(self, evt):
        if evt.get("kind") == "proxy":
            holder = evt.get("holder")
            status = holder if holder in ("self", "external") else "external"
        elif evt.get("kind") == "device":
            status = "self" if evt.get("online") else "offline"
        else:
            return
        self.set_status(status)

    def set_status(self, status):
        if status not in ICONS or status == self._status or not self.icon:
            return
        self._status = status
        try:
            self.icon.icon = ICONS[status]
            self.icon.title = TIPS[status]
        except Exception:
            pass
