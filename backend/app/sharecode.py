# 分享码（ADR-027，体验区 #11）：自有格式 —— "APX5-" + base62(zlib(json)) + "-" + crc16 校验段。
# 有意不用官方格式（官方是加密私货，openflydigi 都没破）：我们的码只在咱工具之间流通。
import json
import zlib

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
PREFIX = "APX5-"


def _b62_encode(data):
    num = int.from_bytes(data, "big")
    if num == 0:
        return ALPHABET[0]
    out = []
    while num:
        num, rem = divmod(num, 62)
        out.append(ALPHABET[rem])
    return "".join(reversed(out))


def _b62_decode(text):
    num = 0
    for ch in text:
        idx = ALPHABET.index(ch)          # ValueError → 分享码损坏
        num = num * 62 + idx
    return num.to_bytes((num.bit_length() + 7) // 8, "big")


def _crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode(payload: dict):
    """dict → 分享码。payload 期望 {"kind": "profile"|"macro", ...}。"""
    raw = zlib.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"), 9)
    body = _b62_encode(raw)
    return f"{PREFIX}{body}-{_crc16(raw):04X}"


def decode(code: str):
    code = code.strip().replace(" ", "")
    if not code.startswith(PREFIX):
        raise ValueError("不是 APX5 分享码（缺 APX5- 前缀）")
    body, _, crc = code[len(PREFIX):].rpartition("-")
    if not body or not crc:
        raise ValueError("分享码缺校验段")
    raw = _b62_decode(body if body.isupper() else body)
    if _crc16(raw) != int(crc, 16):
        raise ValueError("校验不符：分享码损坏或抄漏")
    return json.loads(zlib.decompress(raw).decode("utf-8"))
