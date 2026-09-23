# -*- mode: python ; coding: utf-8 -*-
# Apex5 Unleashed Windows 打包配置（onedir：启动快、杀毒误报比 onefile 少）。
# 构建命令（在 backend/ 下执行）：
#   python -m PyInstaller apex5.spec --noconfirm
# 产物：dist/Apex5Unleashed/（整个文件夹即发布物，压 zip 即 Release 资产）
import os
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs

sys.path.insert(0, os.path.join(SPECPATH, "app"))

# 版本号唯一真相源 = 仓库根 VERSION（routers/system.py _app_version / CI 发布 / exe 属性全读它）
_REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
with open(os.path.join(_REPO_ROOT, "VERSION"), encoding="utf-8") as _f:
    APP_VERSION = _f.read().strip()
_GIT_SHA_PATH = os.path.join(_REPO_ROOT, "GIT_SHA")   # CI 构建时落盘，源码态没有

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
    (os.path.join(_REPO_ROOT, "VERSION"), "."),
]
if os.path.exists(_GIT_SHA_PATH):
    datas.append((_GIT_SHA_PATH, "."))


def _ver_info():
    """exe 文件属性（右键→详细信息）的版本资源，数字/字符串版本都从 VERSION 来。"""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable,
        VarFileInfo, VarStruct, VSVersionInfo)
    parts = [int(x) for x in APP_VERSION.split(".")]
    parts = (parts + [0] * 4)[:4]
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=parts, prodvers=parts, mask=0x3F, flags=0x0,
                          OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
        children=[
            StringFileInfo([StringTable("080404b0", [
                StringStruct("CompanyName", "Apex5 Unleashed"),
                StringStruct("FileDescription", "Apex5 Unleashed —— 八爪鱼5 工具箱"),
                StringStruct("FileVersion", ".".join(str(p) for p in parts)),
                StringStruct("ProductName", "Apex5 Unleashed"),
                StringStruct("ProductVersion", APP_VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [2052, 1200])]),
        ])

hiddenimports = [
    # uvicorn 的 loop/protocol 按字符串 importlib 动态选装，静态分析看不见；
    # websockets 是 WS 升级的运行时依赖（requirements 已补，CI 干净环境实测缺它
    # 会 "No supported WebSocket library detected" → 前端一直「无法连接后台」）
    "websockets",
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
    version=_ver_info(),
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
