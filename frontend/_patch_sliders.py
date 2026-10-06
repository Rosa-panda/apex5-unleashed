# -*- coding: utf-8 -*-
# 给全部 <input type="range"/> 补 style={fill(v,min,max)}：花括号配对解析 value，
# 跳过已有 style 的标签；并按文件位置补 import。纯文本机械变换，tsc 兜底验证。
import io
import os
import re

SRC = r"C:\Users\laisn\.claude-ctf-workspace\flydigi-apex5-re\apex5-unleashed\frontend\src"
TARGETS = [
    (r"pages\exp\panels\gyro.tsx", "../../../components/rangeFill"),
    (r"pages\exp\panels\gyrofw.tsx", "../../../components/rangeFill"),
    (r"pages\exp\panels\stickcfg.tsx", "../../../components/rangeFill"),
    (r"pages\exp\panels\stickmap.tsx", "../../../components/rangeFill"),
    (r"pages\Lights.tsx", "../components/rangeFill"),
    (r"pages\Macros.tsx", "../components/rangeFill"),
    (r"pages\Screen.tsx", "../components/rangeFill"),
]


def read_braced(s, i):
    """s[i] == '{' → 返回 (配对内容, 结束索引)。"""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j
    raise ValueError("unbalanced brace")


for rel, imp_path in TARGETS:
    p = os.path.join(SRC, rel)
    s = io.open(p, encoding="utf-8").read()
    if "rangeFill" in s:
        print(rel, "SKIP (already imported)")
        continue
    out = []
    pos = 0
    count = 0
    for m in re.finditer(r'<input type="range"', s):
        start = m.start()
        # 找标签收尾 '/>'（此文件族标签内无字符串含 '/>'）
        end = s.index("/>", m.end()) + 2
        tag = s[start:end]
        if "style=" in tag:
            out.append(s[pos:end])
            pos = end
            continue
        # 解析 min/max/value
        def attr(name):
            k = tag.find(name + "={")
            if k < 0:
                return None
            body, _ = read_braced(tag, k + len(name) + 1)
            return body.strip()
        mn, mx, val = attr("min"), attr("max"), attr("value")
        if mn is None or mx is None or val is None:
            out.append(s[pos:end])
            pos = end
            continue
        new_tag = tag[:-2].rstrip() + f" style={{fill({val}, {mn}, {mx})}} />"
        out.append(s[pos:start])
        out.append(new_tag)
        pos = end
        count += 1
    out.append(s[pos:])
    s2 = "".join(out)
    # 补 import（插到最后一个 import 行之后）
    lines = s2.split("\n")
    last_imp = max(i for i, l in enumerate(lines) if l.startswith("import "))
    lines.insert(last_imp + 1, f"import {{ fill }} from '{imp_path}'")
    s2 = "\n".join(lines)
    io.open(p, "w", encoding="utf-8", newline="").write(s2)
    print(rel, "->", count, "sliders patched")
print("DONE")
