//! 音效：全部在启动时用代码合成（方波 / 噪声 / 正弦），不带任何音频文件。
use macroquad::audio::{load_sound_from_bytes, play_sound, set_sound_volume, stop_sound, PlaySoundParams, Sound};
use std::f32::consts::TAU;

const SR: f32 = 22050.0;

#[derive(Clone, Copy)]
pub enum S {
    Jump,
    Land,
    Bow,
    ArrowHit,
    Gun,
    Dry,
    Tick,
    Reload,
    Gat,
    Hiss,
    Boom,
    Hurt,
    Hit,
    Kill,
    Pick,
    Gate,
    Check,
    Stomp,
    Roar,
    Win,
    Ui,
    UiOk,
    Jet,
}

const COUNT: usize = S::Jet as usize + 1;

/// 确定性白噪声（按采样序号取值，-1..1）
fn nz(i: usize) -> f32 {
    let mut x = (i as u32).wrapping_mul(2654435761) ^ 0x9e37_79b9;
    x ^= x >> 15;
    x = x.wrapping_mul(0x85eb_ca6b);
    x ^= x >> 13;
    (x & 0xffff) as f32 / 32768.0 - 1.0
}

fn sq(f: f32, t: f32) -> f32 {
    if (t * f).fract() < 0.5 {
        1.0
    } else {
        -1.0
    }
}

fn sn(f: f32, t: f32) -> f32 {
    (t * f * TAU).sin()
}

/// 合成一段 16 位单声道 WAV。f(t 秒, u = 进度 0..1, 采样序号) → -1..1；lp > 0 时过一阶低通。
fn build(dur: f32, lp: f32, f: impl Fn(f32, f32, usize) -> f32) -> Vec<u8> {
    let n = (dur * SR) as usize;
    let data_len = (n * 2) as u32;
    let mut out = Vec::with_capacity(44 + n * 2);
    out.extend_from_slice(b"RIFF");
    out.extend_from_slice(&(36 + data_len).to_le_bytes());
    out.extend_from_slice(b"WAVEfmt ");
    out.extend_from_slice(&16u32.to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes()); // PCM
    out.extend_from_slice(&1u16.to_le_bytes()); // 单声道
    out.extend_from_slice(&(SR as u32).to_le_bytes());
    out.extend_from_slice(&(SR as u32 * 2).to_le_bytes());
    out.extend_from_slice(&2u16.to_le_bytes());
    out.extend_from_slice(&16u16.to_le_bytes());
    out.extend_from_slice(b"data");
    out.extend_from_slice(&data_len.to_le_bytes());
    let mut prev = 0.0f32;
    for i in 0..n {
        let t = i as f32 / SR;
        let u = t / dur;
        let mut v = f(t, u, i);
        if lp > 0.0 {
            prev += (v - prev) * lp;
            v = prev;
        }
        // 首尾各 3ms 淡入淡出，避免爆音
        let edge = (t / 0.003).min((dur - t) / 0.003).clamp(0.0, 1.0);
        let s = (v * edge).clamp(-1.0, 1.0) * 30000.0;
        out.extend_from_slice(&(s as i16).to_le_bytes());
    }
    out
}

fn synth(s: S) -> Vec<u8> {
    match s {
        S::Jump => build(0.12, 0.0, |t, u, _| sq(260.0 + 420.0 * u, t) * 0.25 * (1.0 - u)),
        S::Land => build(0.09, 0.25, |_, u, i| nz(i) * 0.7 * (1.0 - u)),
        S::Bow => build(0.16, 0.0, |t, u, _| {
            (sq(180.0 - 90.0 * u, t) * 0.2 + sn(520.0 - 300.0 * u, t) * 0.3) * (1.0 - u).powi(2)
        }),
        S::ArrowHit => build(0.07, 0.5, |t, u, i| (nz(i) * 0.5 + sq(140.0, t) * 0.2) * (1.0 - u)),
        S::Gun => build(0.22, 0.45, |t, u, i| {
            (nz(i) * 0.9 * (1.0 - u).powi(3) + sn(90.0 - 50.0 * u, t) * 0.6 * (1.0 - u)).clamp(-1.0, 1.0)
        }),
        S::Dry => build(0.035, 0.0, |t, u, _| sq(1400.0, t) * 0.2 * (1.0 - u)),
        S::Tick => build(0.03, 0.0, |t, u, _| sq(900.0, t) * 0.22 * (1.0 - u)),
        S::Reload => build(0.14, 0.0, |t, u, _| sq(if u < 0.5 { 500.0 } else { 760.0 }, t) * 0.22 * (1.0 - u * 0.6)),
        S::Gat => build(0.05, 0.6, |t, u, i| (nz(i) * 0.6 + sq(110.0, t) * 0.25) * (1.0 - u).powi(2)),
        S::Hiss => build(0.7, 0.0, |_, u, i| (nz(i) - nz(i + 1)) * 0.22 * (1.0 - u)),
        S::Boom => build(0.6, 0.12, |t, u, i| {
            (nz(i) * 1.6 * (1.0 - u).powi(2) + sn(55.0 - 25.0 * u, t) * 0.8 * (1.0 - u)).clamp(-1.0, 1.0)
        }),
        S::Hurt => build(0.2, 0.0, |t, u, _| sq(320.0 - 200.0 * u, t) * 0.3 * (1.0 - u)),
        S::Hit => build(0.045, 0.0, |t, u, _| sq(640.0, t) * 0.18 * (1.0 - u)),
        S::Kill => build(0.14, 0.0, |t, u, _| sq(300.0 + 500.0 * u, t) * 0.22 * (1.0 - u)),
        S::Pick => build(0.18, 0.0, |t, u, _| sq(if u < 0.33 { 660.0 } else if u < 0.66 { 880.0 } else { 1320.0 }, t) * 0.2),
        S::Gate => build(0.4, 0.2, |t, u, i| (nz(i) * 0.5 + sq(70.0 + 30.0 * u, t) * 0.4) * (1.0 - u)),
        S::Check => build(0.3, 0.0, |t, u, _| sn(if u < 0.5 { 523.0 } else { 784.0 }, t) * 0.35 * (1.0 - u * 0.5)),
        S::Stomp => build(0.45, 0.1, |t, u, i| {
            (nz(i) * 1.4 * (1.0 - u).powi(3) + sn(48.0, t) * 0.9 * (1.0 - u)).clamp(-1.0, 1.0)
        }),
        S::Roar => build(0.9, 0.18, |t, u, i| {
            let env = (u * 6.0).min(1.0) * (1.0 - u);
            (sq(62.0 + 14.0 * sn(7.0, t), t) * 0.5 + nz(i) * 0.5) * env * 1.6
        }),
        S::Win => build(0.9, 0.0, |t, u, _| {
            let notes = [523.0, 659.0, 784.0, 1047.0, 784.0, 1047.0];
            let k = ((u * 6.0) as usize).min(5);
            sq(notes[k], t) * 0.2 * (1.0 - u * 0.4)
        }),
        S::Ui => build(0.03, 0.0, |t, u, _| sq(700.0, t) * 0.15 * (1.0 - u)),
        S::UiOk => build(0.08, 0.0, |t, u, _| sq(if u < 0.5 { 700.0 } else { 1050.0 }, t) * 0.18 * (1.0 - u * 0.5)),
        // 循环播放：时长取低频正弦的整数个周期，首尾相接不跳变
        S::Jet => build(0.5, 0.3, |t, _, i| nz(i) * 0.5 + sn(60.0, t) * 0.3),
    }
}

const ALL: [S; COUNT] = [
    S::Jump,
    S::Land,
    S::Bow,
    S::ArrowHit,
    S::Gun,
    S::Dry,
    S::Tick,
    S::Reload,
    S::Gat,
    S::Hiss,
    S::Boom,
    S::Hurt,
    S::Hit,
    S::Kill,
    S::Pick,
    S::Gate,
    S::Check,
    S::Stomp,
    S::Roar,
    S::Win,
    S::Ui,
    S::UiOk,
    S::Jet,
];

pub struct Sfx {
    snd: Vec<Option<Sound>>,
    pub vol: f32,
    jet_on: bool,
}

impl Sfx {
    pub async fn new() -> Sfx {
        let mut snd = Vec::with_capacity(COUNT);
        for s in ALL {
            snd.push(load_sound_from_bytes(&synth(s)).await.ok());
        }
        Sfx { snd, vol: 0.7, jet_on: false }
    }

    pub fn play(&self, s: S) {
        self.play_v(s, 1.0);
    }

    pub fn play_v(&self, s: S, k: f32) {
        if self.vol <= 0.0 {
            return;
        }
        if let Some(Some(snd)) = self.snd.get(s as usize) {
            play_sound(snd, PlaySoundParams { looped: false, volume: (self.vol * k).clamp(0.0, 1.0) });
        }
    }

    /// 喷气背包的循环声：v = 推力 0..1，0 即停
    pub fn jet(&mut self, v: f32) {
        let Some(Some(snd)) = self.snd.get(S::Jet as usize) else {
            return;
        };
        let vol = (v * self.vol * 0.6).clamp(0.0, 1.0);
        if vol > 0.02 {
            if !self.jet_on {
                play_sound(snd, PlaySoundParams { looped: true, volume: vol });
                self.jet_on = true;
            } else {
                set_sound_volume(snd, vol);
            }
        } else if self.jet_on {
            stop_sound(snd);
            self.jet_on = false;
        }
    }
}
