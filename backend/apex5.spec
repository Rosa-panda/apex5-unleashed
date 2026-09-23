# -*- mode: python ; coding: utf-8 -*-
# Apex5 Unleashed Windows 打包配置（onedir：启动快、杀毒误报比 onefile 少）。
# 构建命令（在 backend/ 下执行）：
#   python -m PyInstaller apex5.spec --noconfirm
# 产物：dist/Apex5Unleashed/（整个文件夹即发布物，压 zip 即 Release 资产）
import os
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs

sys.path.insert(0, os.path.join(SPECPATH, "app"))

# exe 图标复用运行时自绘逻辑（icon.pad_image），构建期生成到 build 目录，不入库
import icon as icon_mod
_ico = icon_mod.ensure_ico(os.path.join(SPECPATH, "build", "app.ico"))

datas = [
    # 前端已构建产物（main.py frozen 分支按 _MEIPASS/frontend/dist 找，构建前先 npm run build）
    (os.path.join(SPECPATH, "..", "frontend", "dist"), "frontend/dist"),
    # 内置游戏档案/预设：源码态按模块 __file__ 同级找（gameprofiles.py:51 / presets.py:17），
    # frozen 下纯模块 __file__ = _MEIPASS/xxx.py，同级即 _MEIPASS 根
    (os.path.join(SPECPATH, "app", "games"), "games"),
    (os.path.join(SPECPATH, "app", "presets"), "presets"),
]

hiddenimports = [
    # uvicorn 的 loop/protocol 按字符串 importlib 动态选装，静态分析看不见
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    # pystray Windows 后端按平台字符串导入
    "pystray._win32",
    # pywebview Windows 后端（WinForms + WebView2，走 pythonnet/clr_loader）
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr_loader",
    "clr_loader.netfx",
    "pythonnet",
]

a = Analysis(
    ["launcher.py"],
    pathex=[os.path.join(SPECPATH, "app")],
    binaries=collect_dynamic_libs("hid") + collect_dynamic_libs("webview")
             + collect_dynamic_libs("clr_loader"),
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Apex5Unleashed",
    icon=_ico,
    debug=False,
    strip=False,
    upx=False,
    console=False,          # 无黑窗（日志全在 %APPDATA%\Apex5Unleashed\apex5.log）
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Apex5Unleashed",
)
