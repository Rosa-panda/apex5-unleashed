# 应用图标：程序化手柄图形（自绘 = 零版权风险），窗口 .ico 与托盘共用一套绘制。
import os
from PIL import Image, ImageDraw

_BG = (10, 10, 15, 255)          # 深底（与 UI 同色系）
_FG = {                           # 三态前景色（与托盘旧色板一致）
    "self": (34, 211, 238, 255),      # 青：正常
    "external": (245, 158, 11, 255),  # 橙：被接管
    "offline": (107, 114, 128, 255),  # 灰：无设备
}
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def pad_image(status="self", size=64):
    """画一个手柄：深底圆角方 + 手柄轮廓 + 左十字键 + 右四键。size 任意（矢量式按比例绘制）。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = size / 64.0
    d.rounded_rectangle([3 * u, 3 * u, 61 * u, 61 * u], radius=14 * u, fill=_BG)
    fg = _FG.get(status, _FG["self"])

    # 手柄身体：横向胶囊 + 左右握把
    d.rounded_rectangle([13 * u, 23 * u, 51 * u, 41 * u], radius=9 * u, fill=fg)
    d.ellipse([9 * u, 26 * u, 29 * u, 48 * u], fill=fg)
    d.ellipse([35 * u, 26 * u, 55 * u, 48 * u], fill=fg)

    # 左十字键（挖空）
    dk = _BG
    d.rounded_rectangle([19.5 * u, 27 * u, 24.5 * u, 39 * u], radius=1.5 * u, fill=dk)
    d.rounded_rectangle([15 * u, 30.5 * u, 29 * u, 35.5 * u], radius=1.5 * u, fill=dk)

    # 右侧四键（挖空）
    for cx, cy in ((42.5, 28.5), (46.5, 32.5), (42.5, 36.5), (38.5, 32.5)):
        r = 2.2 * u
        d.ellipse([(cx * u - r), (cy * u - r), (cx * u + r), (cy * u + r)], fill=dk)

    # 中部两个小菜单键
    for cx in (30.5, 33.5):
        r = 1.4 * u
        d.ellipse([(cx * u - r), (28.6 * u - r), (cx * u + r), (28.6 * u + r)], fill=dk)
    return img


def ico_path():
    """多尺寸 .ico 落盘位置（APPDATA，避免污染仓库）。"""
    d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                     "Apex5Unleashed")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "app.ico")


def ensure_ico(path=None):
    """生成/刷新多尺寸 .ico，返回路径；失败返回 None（窗口图标缺失可容忍）。"""
    try:
        p = path or ico_path()
        pad_image("self", 256).save(p, format="ICO", sizes=ICO_SIZES)
        return p
    except Exception:
        return None
