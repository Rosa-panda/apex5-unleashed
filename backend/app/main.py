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
    """线程D：2s 热插拔轮询 + 代理进程扫描 + 30s 电量心跳。"""
    batt_tick = 0
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
        # 电量心跳 ~30s 一发（attach 时有首发；回复异步进 _capture_battery）。
        # ⚠ 手柄静默时必须停发：固件把主机 report 当活动，30s 心跳会不断重置
        # 空闲计时 → 手柄永不休眠（2026-09-22 用户实锤，与 0xEF 流常开同因）。
        # 活动判据 = 手柄主动上报（engine.last_input：0xEF 流/vendor 原始帧 +
        # keymonitor.last_input：键盘/游戏盘接口输入），**不含本方请求的 ACK
        # 回复**——否则心跳自己维持自己成死循环。挂机最迟 60s 停发（挂机期间
        # 电量时间戳不刷新属预期，手柄已睡）；唤醒按键后 ≤2s 恢复刷新。
        batt_tick += 1
        if eng.online and batt_tick >= 15:
            import keymonitor as _km
            last_touch = max(eng.last_input, _km.last_input)
            if time.monotonic() - last_touch < 60.0:
                batt_tick = 0
                eng.refresh_battery()
        eng._stop.wait(2.0)


def main():
    _boot_t0 = time.monotonic()          # 启动计时（run_gui.pyw 的 [boot] 日志配套）
    try:
        # 任务栏图标归组身份：不显式声明 AUMID，Windows 按 pythonw.exe 归组 →
        # 任务栏永远显示 python 默认图标（窗口图标设了也没用，2026-09-20 用户实测）
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RosaPanda.Apex5Unleashed")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="无手柄 Mock 模式")
    ap.add_argument("--no-gui", action="store_true", help="无窗口（开发/CI）")
    ap.add_argument("--port", type=int, default=18765)
    args = ap.parse_args()

    eng = engine_mod.Engine(force_mock=args.mock)
    store = presets_mod.PresetStore()
    games = gameprofiles.GameProfiles(store)
    # DSX ingress + Mod 管家（ADR-025）：7878 收官方 Mod 的 DSX 事件流 → cmd51；
    # mod 生命周期由前台事件驱动（挂 games.subscribers，不占独立轮询线程）
    import dsxingress as dsx_mod
    import modmgr as modmgr_mod
    ingress = dsx_mod.DsxIngress(lambda: eng)
    mods = modmgr_mod.ModManager(lambda: eng, games, ingress)
    ui_hooks = {"show": None}          # main 后半段窗口就绪后填入（/api/show 二次启动唤起用）
    app = service.create_app(eng, store, games, ui_hooks=ui_hooks, mods=mods, ingress=ingress)

    # 静态前端（存在才挂）
    import os
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend", "dist")
    if os.path.isdir(web_dir):
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        _index = os.path.join(os.path.abspath(web_dir), "index.html")
        # index.html 必须 no-cache：它引用带 hash 的 assets（可长缓存），但自身一旦被
        # WebView2/浏览器缓存，发新版后窗口还拿旧入口 → 404 或跑旧 JS——「改了没生效」
        # 的元凶（2026-09-21 用户实测：部署多轮界面始终旧版）。
        @app.get("/index.html", include_in_schema=False)
        def _index_nc():
            return FileResponse(_index, headers={"Cache-Control": "no-cache"})

        @app.get("/", include_in_schema=False)
        def _root_nc():
            return FileResponse(_index, headers={"Cache-Control": "no-cache"})

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

    # 起 uvicorn：**绑定重试 + 认自家标志**。三种端口状态三种处置——
    #   ① 活实例在服务 → 唤起它的窗口，本进程退出（防双开）
    #   ② 端口被垂死旧进程占着（刚退出还没放）→ 每 0.5s 重试绑定，等它放了就起
    #      （2026-09-20 用户实测：退出后立刻重启 → 10048 → 干等 10s 弹错，启动"非常慢"的元凶）
    #   ③ 重试用尽仍不行 → 弹窗报错退出，绝不带病开窗
    # 绑定失败时 uvicorn 在子线程里 sys.exit 静默死亡，必须认 server.started（自家标志），
    # 不能只探 health——那会把别人家的后台当成自己的（双开两窗口的老 bug）。
    server = None
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        try:                            # 活实例？唤起并退出
            urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health", timeout=0.5)
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/show", timeout=1.0)
            except Exception:
                pass
            return
        except Exception:
            pass
        srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1",
                                            port=args.port, log_level="warning"))
        t = threading.Thread(target=srv.run, daemon=True, name="uvicorn")
        t.start()
        while time.monotonic() < deadline:       # 等到起来或线程死（绑挂），不设短超时
            if srv.started:
                server = srv
                break
            if not t.is_alive():
                break                            # 绑定失败（10048），线程已死 → 重试
            time.sleep(0.05)
        if server:
            print(f"[boot] uvicorn 就绪 +{time.monotonic() - _boot_t0:.1f}s")
            break
        time.sleep(0.5)
    if not server:
        msg = (f"后台启动失败：端口 {args.port} 持续被占用（可能有残留进程）。\n"
               "请用任务管理器结束残留的 python/pythonw 进程后重新打开本软件。")
        print(f"[boot] 绑定失败放弃，共耗时 {time.monotonic() - _boot_t0:.1f}s")
        print(msg)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, "Apex5 Unleashed", 0x10)
        except Exception:
            pass
        return                          # 绝不带病开窗

    threading.Thread(target=monitor_loop, args=(eng, args.mock), daemon=True, name="monitor").start()
    games.start_watch(eng, eng._stop)          # 前台游戏自动切换（ADR-014）
    if ingress.start():                        # 7878（被占则 8787）收 DSX 事件流
        games.subscribers.append(mods.on_foreground)
        print(f"[boot] DSX ingress 就绪 :{ingress.port}")
    else:
        # 端口被占大概率是飞智空间站服务在跑——只报一次，不挡主流程
        print(f"[boot] DSX ingress 未启动: {ingress.error}")
        eng._emit("error", detail=ingress.error)

    # 飞智虚拟手柄抢 XInput 0 号槽（原神等只认 0 号槽的游戏不震，2026-09-20 实锤）。
    # 检测驱动，不是开关：开了「自动修复」后，启动时 + 每次进游戏时查一次设备树，
    # 检测到它活跃才出手——且默认是**临时修复**（哨兵在软件退出时自动还原，
    # 不留永久改动）；永久禁用只在设置页被显式点击时发生。
    import vibfix as vibfix_mod

    if vibfix_mod.needs_selfheal():
        # 上次会话是临时修复但软件没走正常退出（崩溃/重启杀了哨兵）。
        # 自动修复开着 → 禁用马上还要重建，残留续用即可（省一次 UAC）；
        # 自动修复关着 → 启动自愈还原原状，绝不留下用户不知情的禁用。
        if games.vibfix_auto:
            vibfix_mod.ledger_record("temporary", "disabled")
            eng._emit("vibfix", state="carryover",
                      detail="上次会话的临时修复残留继续生效（自动修复开启，保持禁用）")
        else:
            eng._emit("vibfix", state="selfheal",
                      detail="检测到上次会话临时修复的残留（本软件未正常退出），正在请求授权恢复原状…")
            if vibfix_mod.restore():
                eng._emit("vibfix", state="restored", detail="虚拟手柄已恢复，系统回到原始状态")

    def vibfix_watch(_exe):
        if not (games.vibfix_auto and vibfix_mod.auto_fix_allowed()):
            return
        if vibfix_mod.status() != "enabled":
            return
        eng._emit("vibfix", state="fixing",
                  detail="检测到飞智虚拟手柄占用 XInput 0 号槽（会吞游戏震动），正在请求授权临时修复…")
        if vibfix_mod.auto_disable():
            eng._emit("vibfix", state="fixed",
                      detail="已授权临时禁用虚拟手柄，真手柄独占震动；本软件退出后会自动恢复原状")
        else:
            eng._emit("vibfix", state="denied",
                      detail="未获授权，虚拟手柄仍在抢震动；可到设置页手动修复，或关闭自动修复避免再次询问")

    games.subscribers.append(vibfix_watch)
    if games.vibfix_auto:
        vibfix_watch(None)                 # 启动时也查一次（游戏内启动本工具的场景）
    try:                                       # 封面图后台预下载（gameimg，失败不影响主流程）
        import gameimg
        gameimg.start_prefetch(games)
    except Exception as _e:
        print(f"img prefetch 不可用（忽略）: {_e}")
    if not args.mock:
        import keymonitor
        keymonitor.KeyMonitor(eng._emit).start()   # 特殊键监听（键盘接口）
        keymonitor.GamepadRawMonitor(eng._emit).start()   # 拓展键（游戏盘接口填充字节，实锤见 PROTOCOL.md）

    if args.no_gui:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            mods.stop_mod()
            eng.panic(source="exit")
            eng.stop()
        return

    import tray as tray_mod

    # WebView2 默认遵循系统代理。用户系统代理若半死（监听着但转发不了），会出现
    # 诡异症状：GET 能过、带 body 的 POST 永不返回（2026-09-21 用户实测总闸
    # 「切换中」卡死）。本应用窗口只访问自家的 127.0.0.1 后台——直接禁代理，
    # 彻底拔掉这个变量。必须在 webview 创建浏览器进程前设置。
    import os as _os
    _os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--no-proxy-server")

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
        # ⚠ 第一时间停 uvicorn：退出中的实例若还在答 /api/health，刚启动的新实例
        # 会误判"已有实例在跑"→ 唤起一个正在死掉的窗口 → 两头都没窗口（2026-09-20）。
        _quitting["v"] = True
        try:
            server.should_exit = True
        except Exception:
            pass
        mods.stop_mod()                       # 退出前杀 mod 子进程（别留孤儿继续发包）
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

    # 窗口/任务栏图标：自绘手柄 .ico（icon.py，零版权风险）。native Form 在 webview
    # 启动后才存在，挂 loaded 事件设置；失败静默（缺图标可容忍）。
    import icon as icon_mod
    ico = icon_mod.ensure_ico()
    if ico:
        def _apply_win_icon():
            try:
                from System.Drawing import Icon
                window.native.Icon = Icon(ico)
                # ⚠ 只做纯赋值：ShowInTaskbar 之类会重建句柄的属性必须 UI 线程改，
                # 在事件线程改 = 死锁（py-spy 实锤：MainThread 等 create_window、
                # 事件线程等 UI 线程，全进程 GIL 僵死，2026-09-20）。
            except Exception:
                pass
        window.events.loaded += _apply_win_icon

    webview.start()          # 主线程阻塞（Windows 要求；X 只隐藏，退出走角标）
    print("[boot] webview 返回，进程收尾")
    mods.stop_mod()
    ingress.stop()
    eng.panic(source="exit")
    eng.stop()


if __name__ == "__main__":
    main()
