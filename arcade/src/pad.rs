//! 输入：XInput 手柄（运行时动态加载 dll，不依赖导入库）+ 键盘兜底，合成一份 `Input`。
//! 震动输出也走这里（XInputSetState）。
//!
//! 飞智空间站的虚拟手柄可能占着 0 号槽，所以不认死某个槽位：
//! 输入取所有已连接手柄的合并值，震动发给所有已连接手柄。
use macroquad::prelude::*;
use std::ffi::c_void;

#[repr(C)]
#[derive(Default, Clone, Copy)]
struct XGamepad {
    buttons: u16,
    lt: u8,
    rt: u8,
    lx: i16,
    ly: i16,
    rx: i16,
    ry: i16,
}

#[repr(C)]
#[derive(Default, Clone, Copy)]
struct XState {
    packet: u32,
    pad: XGamepad,
}

#[repr(C)]
struct XVib {
    lo: u16,
    hi: u16,
}

type GetState = unsafe extern "system" fn(u32, *mut XState) -> u32;
type SetState = unsafe extern "system" fn(u32, *mut XVib) -> u32;

#[link(name = "kernel32")]
extern "system" {
    fn LoadLibraryA(name: *const u8) -> *mut c_void;
    fn GetProcAddress(module: *mut c_void, name: *const u8) -> *mut c_void;
}

struct XInput {
    get: GetState,
    set: SetState,
}

impl XInput {
    fn load() -> Option<XInput> {
        for dll in ["xinput1_4.dll\0", "xinput1_3.dll\0", "xinput9_1_0.dll\0"] {
            // SAFETY: 传入的是以 NUL 结尾的静态字符串；返回的函数指针签名与 XInput 文档一致
            unsafe {
                let h = LoadLibraryA(dll.as_ptr());
                if h.is_null() {
                    continue;
                }
                let g = GetProcAddress(h, "XInputGetState\0".as_ptr());
                let s = GetProcAddress(h, "XInputSetState\0".as_ptr());
                if g.is_null() || s.is_null() {
                    continue;
                }
                return Some(XInput {
                    get: std::mem::transmute::<*mut c_void, GetState>(g),
                    set: std::mem::transmute::<*mut c_void, SetState>(s),
                });
            }
        }
        None
    }
}

const B_UP: u16 = 0x0001;
const B_DOWN: u16 = 0x0002;
const B_LEFT: u16 = 0x0004;
const B_RIGHT: u16 = 0x0008;
const B_START: u16 = 0x0010;
const B_BACK: u16 = 0x0020;
const B_LB: u16 = 0x0100;
const B_RB: u16 = 0x0200;
const B_A: u16 = 0x1000;
const B_B: u16 = 0x2000;
const B_X: u16 = 0x4000;

/// 一帧的输入快照。`_p` 结尾的是「刚按下」的边沿。
#[derive(Default, Clone, Copy)]
pub struct Input {
    /// 水平移动 -1..1
    pub mx: f32,
    /// 垂直瞄准，向上为正 -1..1
    pub my: f32,
    pub jump: bool,
    pub jump_p: bool,
    /// 右扳机 0..1（射击）
    pub rt: f32,
    /// 左扳机 0..1（喷气背包）
    pub lt: f32,
    pub next_w: bool,
    pub prev_w: bool,
    /// 直接选武器（键盘 1/2/3）
    pub pick_w: Option<usize>,
    pub reload: bool,
    pub pause: bool,
    pub debug: bool,
    /// F5：重新读取档案里的手感配置
    pub reload_cfg: bool,
    pub confirm: bool,
    pub back: bool,
    /// 菜单方向边沿：-1 / 0 / 1
    pub menu_x: i32,
    pub menu_y: i32,
}

pub struct Pad {
    xi: Option<XInput>,
    slots: [bool; 4],
    scan_t: f32,
    prev_btn: u16,
    prev_dir: (i32, i32),
    kb_rt: f32,
    kb_lt: f32,
    vib: (u16, u16),
    vib_t: f64,
}

fn stick(v: i16) -> f32 {
    let f = v as f32 / 32767.0;
    let dead = 0.22;
    if f.abs() < dead {
        0.0
    } else {
        (f.abs() - dead) / (1.0 - dead) * f.signum()
    }
}

impl Pad {
    pub fn new() -> Pad {
        Pad {
            xi: XInput::load(),
            slots: [false; 4],
            scan_t: 0.0,
            prev_btn: 0,
            prev_dir: (0, 0),
            kb_rt: 0.0,
            kb_lt: 0.0,
            vib: (0, 0),
            vib_t: 0.0,
        }
    }

    /// 已连接的手柄数量
    pub fn connected(&self) -> u32 {
        self.slots.iter().filter(|s| **s).count() as u32
    }

    pub fn poll(&mut self, dt: f32) -> Input {
        let mut btn = 0u16;
        let (mut lt, mut rt) = (0.0f32, 0.0f32);
        let (mut lx, mut ly) = (0.0f32, 0.0f32);
        if let Some(xi) = &self.xi {
            // 对未连接槽位调 XInputGetState 很慢：每秒才重扫一次
            self.scan_t -= dt;
            let rescan = self.scan_t <= 0.0;
            if rescan {
                self.scan_t = 1.0;
            }
            for i in 0..4 {
                if !self.slots[i] && !rescan {
                    continue;
                }
                let mut st = XState::default();
                // SAFETY: st 是合法的可写 XINPUT_STATE；槽位号在 0..4
                let ok = unsafe { (xi.get)(i as u32, &mut st) } == 0;
                self.slots[i] = ok;
                if !ok {
                    continue;
                }
                btn |= st.pad.buttons;
                lt = lt.max(st.pad.lt as f32 / 255.0);
                rt = rt.max(st.pad.rt as f32 / 255.0);
                let (x, y) = (stick(st.pad.lx), stick(st.pad.ly));
                if x.abs() > lx.abs() {
                    lx = x;
                }
                if y.abs() > ly.abs() {
                    ly = y;
                }
            }
        }
        if btn & B_LEFT != 0 {
            lx = -1.0;
        }
        if btn & B_RIGHT != 0 {
            lx = 1.0;
        }
        if btn & B_UP != 0 {
            ly = 1.0;
        }
        if btn & B_DOWN != 0 {
            ly = -1.0;
        }

        // 键盘兜底。扳机是模拟量：J 按住时 RT 缓慢爬升（才能体现拉弓 / 二段），松开归零
        let kl = is_key_down(KeyCode::A) || is_key_down(KeyCode::Left);
        let kr = is_key_down(KeyCode::D) || is_key_down(KeyCode::Right);
        let ku = is_key_down(KeyCode::W) || is_key_down(KeyCode::Up);
        let kd = is_key_down(KeyCode::S) || is_key_down(KeyCode::Down);
        if kl {
            lx = -1.0;
        }
        if kr {
            lx = 1.0;
        }
        if ku {
            ly = 1.0;
        }
        if kd {
            ly = -1.0;
        }
        self.kb_rt = if is_key_down(KeyCode::J) { (self.kb_rt + 1.6 * dt).min(1.0) } else { 0.0 };
        self.kb_lt = if is_key_down(KeyCode::K) { (self.kb_lt + 5.0 * dt).min(1.0) } else { 0.0 };
        rt = rt.max(self.kb_rt);
        lt = lt.max(self.kb_lt);

        let pressed = btn & !self.prev_btn;
        self.prev_btn = btn;
        let dir = (
            if lx < -0.5 { -1 } else if lx > 0.5 { 1 } else { 0 },
            if ly > 0.5 { -1 } else if ly < -0.5 { 1 } else { 0 }, // 菜单里向上 = 上一项
        );
        let menu_x = if dir.0 != self.prev_dir.0 { dir.0 } else { 0 };
        let menu_y = if dir.1 != self.prev_dir.1 { dir.1 } else { 0 };
        self.prev_dir = dir;

        let pick_w = if is_key_pressed(KeyCode::Key1) {
            Some(0)
        } else if is_key_pressed(KeyCode::Key2) {
            Some(1)
        } else if is_key_pressed(KeyCode::Key3) {
            Some(2)
        } else {
            None
        };

        Input {
            mx: lx.clamp(-1.0, 1.0),
            my: ly.clamp(-1.0, 1.0),
            jump: btn & B_A != 0 || is_key_down(KeyCode::Space),
            jump_p: pressed & B_A != 0 || is_key_pressed(KeyCode::Space),
            rt,
            lt,
            next_w: pressed & B_RB != 0 || is_key_pressed(KeyCode::E),
            prev_w: pressed & B_LB != 0 || is_key_pressed(KeyCode::Q),
            pick_w,
            reload: pressed & B_X != 0 || is_key_pressed(KeyCode::R),
            pause: pressed & B_START != 0 || is_key_pressed(KeyCode::Escape),
            debug: pressed & B_BACK != 0 || is_key_pressed(KeyCode::F1),
            reload_cfg: is_key_pressed(KeyCode::F5),
            confirm: pressed & B_A != 0 || is_key_pressed(KeyCode::Enter) || is_key_pressed(KeyCode::Space),
            back: pressed & B_B != 0 || is_key_pressed(KeyCode::Escape),
            menu_x,
            menu_y,
        }
    }

    /// 设置震动（0..1）。只在数值变化时下发，且限频，避免每帧打驱动。
    pub fn rumble(&mut self, lo: f32, hi: f32, now: f64) {
        let v = ((lo.clamp(0.0, 1.0) * 65535.0) as u16, (hi.clamp(0.0, 1.0) * 65535.0) as u16);
        if v == self.vib {
            return;
        }
        let stopping = v == (0, 0);
        if !stopping && now - self.vib_t < 0.012 {
            return;
        }
        self.vib = v;
        self.vib_t = now;
        self.push_vib();
    }

    /// 立刻停震（退出 / 暂停）
    pub fn rumble_off(&mut self) {
        self.vib = (0, 0);
        self.push_vib();
    }

    fn push_vib(&self) {
        if let Some(xi) = &self.xi {
            for i in 0..4 {
                if self.slots[i] {
                    let mut v = XVib { lo: self.vib.0, hi: self.vib.1 };
                    // SAFETY: v 是合法的 XINPUT_VIBRATION；槽位号在 0..4
                    unsafe {
                        (xi.set)(i as u32, &mut v);
                    }
                }
            }
        }
    }
}
