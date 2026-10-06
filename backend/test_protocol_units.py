# -*- coding: utf-8 -*-
r"""`protocol.py` 纯函数单测（T04.1，TEST-PLAN「CI 策略」第 1 项）。

覆盖：帧构造 / CRC / ACK 解析 / 扳机 payload 与钳位 / grip payload / Mock ACK 电量字节 /
灯效生成器帧对齐 / 灯表槽位容量裁剪。**全部纯 Mock，0 个用例需要真机**。

运行：
    python -m pytest backend/test_protocol_units.py -v
    python backend/test_protocol_units.py      # 等价于跑上面那条
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import engine
import protocol as p


# ---------- helpers ----------

def _params_for(mode, over=None):
    """按 TRIGGER_MODES 的字段表造一份「全部给上界」的参数（保证每个字段都被覆盖到）。"""
    params = {f[0]: f[2] for f in p.TRIGGER_MODES[mode]["fields"]}
    params.update(over or {})
    return params


class _StubEngine:
    """只实现 `Engine.led_apply_effect` 用到的接口，用来隔离验证槽位裁剪逻辑。

    不走真 HID：`led_write` 记账、`_emit` 收事件，其余一概不需要。
    """

    def __init__(self, bean):
        self._led_bean = dict(bean)
        self.writes = []      # [(bean, frames_b, source)]
        self.events = []      # [(kind, kwargs)]

    def led_write(self, bean, frames_b, source="ui"):
        self.writes.append((bean, bytes(frames_b), source))

    def _emit(self, kind, **kw):
        self.events.append((kind, kw))


# ---------- 1. trigger_payload ----------

def test_trigger_payload_layout_six_modes():
    """六模式：[apply, side, mode_id, *params]，长度 = 3 + 字段数。"""
    for mode in ("normal", "race", "recoil", "sniper", "lock", "vibration"):
        for apply_ in (True, False):
            for side in (1, 2):
                payload = p.trigger_payload(apply_, side, mode, _params_for(mode))
                assert payload is not None, mode
                assert payload[0] == (1 if apply_ else 0)
                assert payload[1] == side
                assert payload[2] == p.TRIGGER_MODE_IDS[mode]
                assert len(payload) == 3 + len(p.TRIGGER_MODES[mode]["fields"])


def test_trigger_payload_mode_ids_follow_declaration_order():
    """wire 模式号 = TRIGGER_MODES 声明序（ADR-022 勘误后的最终取值，不得漂移）。"""
    assert p.TRIGGER_MODE_IDS == {"normal": 0, "race": 1, "recoil": 2,
                                  "sniper": 3, "lock": 4, "vibration": 5}


def test_trigger_payload_clamps_low():
    payload = p.trigger_payload(True, 1, "race", {"stroke": -1, "resistance": -5, "match": -9})
    # race 三字段下界依次为 1 / 1 / 0
    assert list(payload[3:]) == [1, 1, 0], list(payload)


def test_trigger_payload_clamps_high():
    payload = p.trigger_payload(True, 2, "vibration",
                                {"stroke": 999, "press": 999, "strength": 999,
                                 "freq": 999, "match": 999})
    assert list(payload[3:]) == [255, 255, 255, 255, 1], list(payload)


def test_trigger_payload_missing_field_defaults():
    """缺字段不报错，落到该字段声明的下界（PROTOCOL「缺字段不报错」）。"""
    payload = p.trigger_payload(True, 1, "race", {})
    assert payload is not None
    assert list(payload[3:]) == [1, 1, 0], list(payload)
    # 只给其中一部分时，未给的仍按下界补齐
    partial = p.trigger_payload(True, 1, "race", {"stroke": 120})
    assert list(partial[3:]) == [120, 1, 0], list(partial)


def test_trigger_payload_invalid_mode_returns_none():
    assert p.trigger_payload(True, 1, "nosuchmode", {}) is None


def test_trigger_payload_invalid_side_returns_none():
    """side=3（Both）是被 ACK 但不执行的枚举——协议层就该拒掉，不许传下去。"""
    assert p.trigger_payload(True, 3, "race", _params_for("race")) is None
    assert p.trigger_payload(True, 0, "race", _params_for("race")) is None


# ---------- 2. grip_payload ----------

def test_grip_payload_layout():
    """cmd82：[side, bindType=2, filter, scale, stroke, press, strength, freq]，缺字段补 0。"""
    payload = p.grip_payload(2, {"filter": 4, "scale": 5, "stroke": 6,
                                 "press": 7, "strength": 8, "freq": 9})
    assert list(payload) == [2, 2, 4, 5, 6, 7, 8, 9], list(payload)
    assert list(p.grip_payload(1, {})) == [1, 2, 0, 0, 0, 0, 0, 0]
    # 钳位范围 0..255
    over = p.grip_payload(1, {f[0]: 999 for f in p.GRIP_FIELDS})
    assert list(over[2:]) == [255] * len(p.GRIP_FIELDS), list(over)


# ---------- 3. build / build_crc ----------

def test_build_frame_layout():
    frame = p.build(p.CMD_RUMBLE, bytes([10, 20]))
    assert len(frame) == p.PACKET_LEN == 32
    assert frame[0] == p.REPORT_ID_OUT == 0x03
    assert frame[1] == 0x5A and frame[2] == 0xA5
    assert frame[3] == p.CMD_RUMBLE
    assert frame[4] == 2
    assert frame[5:7] == bytes([10, 20])
    assert frame[7:] == bytes(25)          # 补零到 32B
    # 空 payload 帧
    empty = p.build(p.CMD_INFO)
    assert len(empty) == 32 and empty[4] == 0 and empty[5:] == bytes(27)


def test_build_crc_led_test_manual():
    """CMD_LED_TEST：crc = sum(frame[3:3+len]) & 0xFF，手工算一遍对照实现。"""
    payload = bytes([0xFF, 0x10, 0x20])
    frame = p.build_crc(p.CMD_LED_TEST, payload)
    n = len(payload) + 2                  # cmd + len + payload
    assert frame[4] == n == 5
    manual = (p.CMD_LED_TEST + n + 0xFF + 0x10 + 0x20) & 0xFF
    assert frame[8] == manual, (frame[8], manual)
    assert frame[8] == p.crc8_sum(frame[3:3 + n])
    assert frame[9:] == bytes(32 - 9)     # 补齐 32B 报告


def test_build_crc_length_field_counts_cmd_and_len():
    """len 字段 = payload + 2（cmd 字节与 len 字节自身也算进去），易错点。"""
    for size in (0, 1, 7, 20):
        payload = bytes(range(size))
        frame = p.build_crc(p.CMD_LED_WRITE_PACK, payload)
        assert frame[4] == size + 2
        assert len(frame) == 32


# ---------- 4. ack_ok ----------

def _ack_body(cmd_id, ok=True):
    """剥掉 report id 的 ACK 体（成功位在 [3]）。"""
    return bytes([0x5A, 0xA5, cmd_id, 0x01 if ok else 0x00, 0x00, 0x80] + [0] * 26)


def test_ack_ok_non_k6():
    assert p.ack_ok(_ack_body(p.CMD_TRIGGER), p.CMD_TRIGGER) is True
    assert p.ack_ok(bytes([0x5A, 0xA5, p.CMD_INFO, 0x01]), p.CMD_INFO) is True


def test_ack_ok_cmd_mismatch():
    """cmd 号不匹配必须 False（ACK 广播给所有读者，靠 cmd 号区分）。"""
    assert p.ack_ok(_ack_body(p.CMD_TRIGGER), p.CMD_GRIP) is False
    assert p.ack_ok(_ack_body(p.CMD_TRIGGER, ok=False), p.CMD_TRIGGER) is False


def test_ack_ok_short_frame():
    """帧过短不能抛 IndexError，只能 False。"""
    assert p.ack_ok(b"", p.CMD_TRIGGER) is False
    assert p.ack_ok(b"\x5a\xa5", p.CMD_TRIGGER) is False
    assert p.ack_ok(bytes([0x5A, 0xA5, p.CMD_TRIGGER]), p.CMD_TRIGGER) is False  # len<=3


# ---------- 5. mock_ack_frame ----------

def test_mock_ack_frame_info_carries_battery():
    """cmd1 心跳：body[5]=0x80 设备类型、body[11]=0x04 电量（Mock 电量显示的回归）。"""
    frame = p.mock_ack_frame(p.CMD_INFO)
    assert len(frame) == p.PACKET_LEN
    assert frame[0] == p.REPORT_ID_IN == 0x04
    body = frame[1:]                       # 剥 report id
    assert body[2] == p.CMD_INFO and body[3] == 0x01
    assert body[5] == 0x80                 # 设备类型 = Apex5
    assert body[7:11] == bytes(4)          # MAC（Mock 全零）
    assert body[11] == 0x04                # 电量 4/5
    level = body[11] & 0x0F
    charging = (body[11] >> 4) & 0x0F
    assert level == 4 and charging == 0
    assert p.ack_ok(body, p.CMD_INFO) is True


def test_mock_ack_frame_generic_has_no_battery():
    """普通命令的 Mock ACK 不带电量字节（body[11] 为 0），避免伪造疲劳数据。"""
    frame = p.mock_ack_frame(p.CMD_TRIGGER)
    body = frame[1:]
    assert len(frame) == 32 and body[5] == 0x80
    assert body[11] == 0x00
    assert p.ack_ok(body, p.CMD_TRIGGER) is True


# ---------- 6. 灯效生成器 ----------

_MULTI_COLOR = {"gradient", "flow", "chase", "duosweep", "auroraflow", "aurora"}
_GENERATORS = ["solid", "breath", "gradient", "flow", "blink", "heartbeat", "wipe",
               "comet", "duosweep", "rain", "chase", "pulse", "fire", "auroraflow",
               "typewriter", "aurora"]
# 这几个生成器的第一参数是「单个 rgb 元组」，其余是「颜色列表」
_SINGLE_COLOR = {"solid", "breath", "blink", "heartbeat"}


def test_led_generators_are_frame_aligned():
    """每个生成器的输出长度必须是「帧长(rgb_num*3)」的整数倍且至少一帧——
    半帧会让后续整帧解码错位（写灯前的第一道防线）。"""
    colors = [(255, 0, 0), (0, 0, 255)]
    for name in _GENERATORS:
        gen = getattr(p, "led_frames_" + name)
        for rgb_num in (10, 12, 16):
            if name in _SINGLE_COLOR:
                out = gen(colors[0], rgb_num)
            else:
                out = gen(list(colors), rgb_num)
            frame_len = rgb_num * 3
            assert len(out) > 0, name
            assert len(out) % frame_len == 0, (name, rgb_num, len(out))
            assert len(out) // frame_len >= 1, name


def test_led_slot_capacity_truncates_and_shrinks_frames():
    """槽位容量 = LED_SLOT_BYTES // (rgb_num*3)；超限时 truncated > 0 且帧数据被裁到容量内。

    这里跑的是 `engine.led_apply_effect` 的真实代码（用 _StubEngine 顶替 I/O），
    对应 ADR-033 修订 5 实锤的「写 24 帧只存前 10 帧且旧版自校验不报错」缺陷。
    """
    rgb_num, bean_rgb = 12, {"rgb_num": 12, "version": 3, "brightness": 128,
                             "loop_time": 10, "loop_start": 0, "loop_end": 23}
    stub = _StubEngine(bean_rgb)
    res = engine.Engine.led_apply_effect(stub, "rainbow", [(255, 0, 0)], params=None)

    frame_len = rgb_num * 3
    cap_frames = p.LED_SLOT_BYTES // frame_len          # 360 // 36 = 10
    assert cap_frames == 10
    assert res["ok"] is True
    assert res["frames"] == cap_frames == 10
    assert res["truncated"] > 0                          # rainbow 24 帧 → 截 14 帧
    written_bean, written_frames, _source = stub.writes[0]
    assert len(written_frames) == cap_frames * frame_len == p.LED_SLOT_BYTES
    assert written_bean["loop_end"] == cap_frames - 1    # loop 范围覆盖实写帧
    # truncated 必须同时进账本事件（否则前端看不见告警）
    kind, payload = stub.events[0]
    assert kind == "led" and payload["effect"] == "rainbow"
    assert payload["frames"] == cap_frames and payload["truncated"] == res["truncated"]


def test_led_apply_effect_no_truncation_when_within_capacity():
    """容量内（≤10 帧 @12 灯）的灯效不该报 truncated。"""
    stub = _StubEngine({"rgb_num": 12, "version": 3, "brightness": 128, "loop_time": 10})
    res = engine.Engine.led_apply_effect(stub, "comet", [(0, 170, 255)], params=None)
    # comet = 逐珠点亮 n 帧 = 12 帧 → 12 > 10，会被裁到 10（超限族）
    assert res["truncated"] == 2, res
    stub2 = _StubEngine({"rgb_num": 12, "version": 3, "brightness": 128, "loop_time": 10})
    res2 = engine.Engine.led_apply_effect(stub2, "duosweep", [(0, 170, 255), (255, 0, 140)])
    assert res2["truncated"] == 0, res2      # ceil(12/2)+2 = 8 帧，容量内
    assert res2["frames"] == 8, res2


def test_parse_led_bean_roundtrip():
    """bean → 20B 头 → 解析回来，版本/灯珠数/loop 等字段保持一致。"""
    bean = {"version": 3, "click_feedback": 0, "loop_start": 0, "loop_end": 7,
            "loop_time": 12, "brightness": 200, "rgb_num": 12, "led_mode": 1,
            "grip_sync": True, "raw_version_bytes": (0, 3)}
    blob = p.led_bean_header(bean, bytes(36 * 8))
    assert len(blob) == 20 + 36 * 8
    back = p.parse_led_bean(blob)
    assert back is not None
    assert back["version"] == 3 and back["rgb_num"] == 12 and back["brightness"] == 200
    assert back["loop_end"] == 7 and back["loop_time"] == 12 and back["grip_sync"] == 1
    # 坏数据须返回 None 而不是抛
    assert p.parse_led_bean(bytes(20)) is None
    assert p.parse_led_bean(bytes([0, 9] + [0] * 30)) is None


if __name__ == "__main__":
    sys.exit(0 if __import__("pytest").main([__file__, "-q"]) == 0 else 1)
