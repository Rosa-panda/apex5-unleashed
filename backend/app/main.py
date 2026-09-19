# 进程组装：uvicorn(daemon) → 端口就绪 → webview(主线程) + 托盘 + 设备监控线程D
import argparse
import threading
import time

import uvicorn

import engine as engine_mod
import gameprofiles
import presets as presets_mod
import service
import transport


def monitor_loop(eng, force_mock):
    """线程D：2s 热插拔轮询 + 代理进程扫描。"""
    while not eng._stop.is_set():
        if not eng.online:
            if force_mock:
                eng.attach(transport.MockPad())
            else:
                path = transport.find_device_path()
                if path:
                    try:
                        eng.attach(transport.HidPad(path))
                    except Exception as e:
                        eng._emit("error", detail=f"打开设备失败: {e}")
        else:
            # 枚举级断连核验：读线程的 HID 异常不一定触发（Windows 下设备消失有时
            # 只表现为 read 静默返回空），这里直接查 VID/PID 还在不在系统里。
            if not force_mock and not transport.find_device_path():
                eng.detach("设备从系统消失（HID 枚举不到）")
            else:
                eng.scan_proxy_processes()
                eng.maybe_release_proxy()
        eng._stop.wait(2.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="无手柄 Mock 模式")
    ap.add_argument("--no-gui", action="store_true", help="无窗口（开发/CI）")
    ap.add_argument("--port", type=int, default=18765)
    args = ap.parse_args()

    eng = engine_mod.Engine(force_mock=args.mock)
    store = presets_mod.PresetStore()
    games = gameprofiles.GameProfiles(store)
    ui_hooks = {"show": None}          # main 后半段窗口就绪后填入（/api/show 二次启动唤起用）
    app = service.create_app(eng, store, games, ui_hooks=ui_hooks)

    # 静态前端（存在才挂）
    import os
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend", "dist")
    if os.path.isdir(web_dir):
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=os.path.abspath(web_dir), html=True), name="web")

    # 单实例（TECH-SPEC §7）：已有实例在跑 → 唤起它的窗口后退出。
    # 旧版只静默退出，用户双击快捷方式毫无反馈，像"软件打不开"。
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health", timeout=0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/show", timeout=1.0)
        except Exception:
            pass
        return
    except Exception:
        pass

    try:
        cfg = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
        server = uvicorn.Server(cfg)
        srv_thread = threading.Thread(target=server.run, daemon=True, name="uvicorn")
        srv_thread.start()
    except OSError:
        print("已在运行（端口被占用），退出。")
        return

    threading.Thread(target=monitor_loop, args=(eng, args.mock), daemon=True, name="monitor").start()
    games.start_watch(eng, eng._stop)          # 前台游戏自动切换（ADR-014）
    if not args.mock:
        import keymonitor
        keymonitor.KeyMonitor(eng._emit).start()   # 特殊键监听（键盘接口）
        keymonitor.GamepadRawMonitor(eng._emit).start()   # 拓展键（游戏盘接口填充字节，实锤见 PROTOCOL.md）

    if args.no_gui:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            eng.panic(source="exit")
            eng.stop()
        return

    import tray as tray_mod

    import webview

    window = None
    _quitting = {"v": False}       # 托盘真退出时置位，X 按钮 closing 钩子放行
    _hide_notified = {"done": False}

    def on_show():
        if window:
            try:
                window.show()
                try:
                    window.restore()      # 最小化状态下拉起
                except Exception:
                    pass
            except Exception:
                pass

    ui_hooks["show"] = on_show

    def _on_closing():
        # 成熟软件惯例：点窗口 X = 最小化到托盘（进程保留，后台继续联动），
        # 真退出只走角标菜单「退出」。首次隐藏弹一次气泡告知去向。
        # ⚠ pywebview 6.2.1 语义（event.py）：closing handler 必须返回**字面 False**
        # 才取消关闭——返回 True/None 都是放行。首版返回 True → X 直接关窗退进程，
        # 角标只剩 Windows 幽灵图标，双击"消失"像闪退（2026-09-19 用户实测抓的 bug）。
        if _quitting["v"]:
            return None                  # 托盘退出放行关闭
        try:
            window.hide()
        except Exception:
            pass
        if not _hide_notified["done"]:
            _hide_notified["done"] = True
            try:
                tray.notify_minimized()
            except Exception:
                pass
        return False                     # 字面 False = 取消关闭（窗口已藏进托盘）

    def on_quit():
        # 托盘「退出」必须真退：panic + 停引擎 + 销毁主窗口（否则主线程卡在
        # webview.start() 里，进程赖着不死——2026-09-19 用户实测抓的 bug）。
        # 3s 兜底强杀：万一 destroy 后 webview 仍不返回，也保证进程退出。
        _quitting["v"] = True
        eng.panic(source="exit")
        eng.stop()
        try:
            if window:
                window.destroy()
        except Exception:
            pass
        import os
        t = threading.Timer(3.0, lambda: os._exit(0))
        t.daemon = True
        t.start()

    tray = tray_mod.Tray(eng, on_show, on_quit)
    try:
        tray.start()
    except Exception as e:
        print(f"托盘不可用（忽略）: {e}")

    # 等端口就绪再开窗（防白屏，TECH-SPEC §7 启动顺序）
    import urllib.request
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)

    window = webview.create_window("Apex5 Unleashed", f"http://127.0.0.1:{args.port}/",
                                   width=1180, height=760, min_size=(960, 620))
    window.events.closing += _on_closing
    webview.start()          # 主线程阻塞（Windows 要求；X 只隐藏，退出走角标）
    eng.panic(source="exit")
    eng.stop()


if __name__ == "__main__":
    main()
