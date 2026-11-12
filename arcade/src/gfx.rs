//! 画面基础：调色板、字符画烘焙成的像素精灵、文字队列。
//!
//! 世界画在 320x180 的低分辨率画布上再整数倍放大（像素风）；
//! 文字单独按屏幕分辨率绘制（否则中文在 180 行高度下糊成一团），
//! 所以绘制过程中文字只是入队，画布贴到屏幕之后再统一 `flush`。
use macroquad::prelude::*;

pub const VW: f32 = 320.0;
pub const VH: f32 = 180.0;

pub fn rgb(hex: u32) -> Color {
    Color::new(
        ((hex >> 16) & 255) as f32 / 255.0,
        ((hex >> 8) & 255) as f32 / 255.0,
        (hex & 255) as f32 / 255.0,
        1.0,
    )
}

pub fn rgba(hex: u32, a: f32) -> Color {
    let mut c = rgb(hex);
    c.a = a;
    c
}

pub mod pal {
    pub const INK: u32 = 0x1a1423;
    pub const WHITE: u32 = 0xffffff;
    pub const RED: u32 = 0xe43b44;
    pub const ORANGE: u32 = 0xf77622;
    pub const YELLOW: u32 = 0xfee761;
    pub const GREEN: u32 = 0x63c74d;
    pub const DGREEN: u32 = 0x3e8948;
    pub const CYAN: u32 = 0x2ce8f5;
    pub const BLUE: u32 = 0x3a6ea5;
    pub const PURPLE: u32 = 0x8a4fa3;
    pub const GRAY: u32 = 0x8b9bb4;
    pub const DGRAY: u32 = 0x5a6988;
    pub const BROWN: u32 = 0xb86f50;
    pub const DBROWN: u32 = 0x743f39;
    pub const ROCK: u32 = 0x4b3d63;
    pub const ROCK_D: u32 = 0x372b4d;
    pub const ROCK_L: u32 = 0x6a5788;
    pub const BG_TOP: u32 = 0x0f0b1f;
    pub const BG_BOT: u32 = 0x1f1838;
    pub const BG_FAR: u32 = 0x171130;
    pub const BG_MID: u32 = 0x231b40;
}

/// 字符画里的字符 → 颜色。'.' 和未登记的字符是透明。
const CHARMAP: &[(char, u32)] = &[
    ('k', pal::INK),
    ('w', pal::WHITE),
    ('r', pal::RED),
    ('e', pal::ORANGE),
    ('y', pal::YELLOW),
    ('g', pal::GREEN),
    ('G', pal::DGREEN),
    ('c', pal::CYAN),
    ('b', pal::BLUE),
    ('d', 0x26466d),
    ('p', pal::PURPLE),
    ('m', pal::GRAY),
    ('M', pal::DGRAY),
    ('n', pal::BROWN),
    ('N', pal::DBROWN),
    ('o', 0xf2c9a0),
];

fn bake(rows: &[&str]) -> Texture2D {
    let w = rows.iter().map(|r| r.chars().count()).max().unwrap_or(1).max(1);
    let h = rows.len().max(1);
    let mut img = Image::gen_image_color(w as u16, h as u16, Color::new(0.0, 0.0, 0.0, 0.0));
    for (y, row) in rows.iter().enumerate() {
        for (x, ch) in row.chars().enumerate() {
            if let Some((_, c)) = CHARMAP.iter().find(|(k, _)| *k == ch) {
                img.set_pixel(x as u32, y as u32, rgb(*c));
            }
        }
    }
    let t = Texture2D::from_image(&img);
    t.set_filter(FilterMode::Nearest);
    t
}

pub struct Sprites {
    /// 站立 / 跑1 / 跑2 / 腾空
    pub player: [Texture2D; 4],
    pub slime: [Texture2D; 2],
    pub bat: [Texture2D; 2],
    pub dummy: Texture2D,
    pub turret: Texture2D,
    pub barrel: Texture2D,
    pub heart: Texture2D,
}

const P_TOP: [&str; 10] = [
    "...yyyy...",
    "..yyyyyy..",
    "..yyyywc..",
    "..ooooko..",
    "..oooooo..",
    ".rrrrrr...",
    "..bbbbbb..",
    "..bbbbbbo.",
    "..bbbbbb..",
    "..dddddd..",
];

fn player_frame(legs: [&str; 4]) -> Texture2D {
    let mut rows: Vec<&str> = P_TOP.to_vec();
    rows.extend_from_slice(&legs);
    bake(&rows)
}

impl Sprites {
    fn new() -> Sprites {
        Sprites {
            player: [
                player_frame(["..dd..dd..", "..dd..dd..", "..kk..kk..", "..kk..kk.."]),
                player_frame(["..dd..dd..", ".dd....dd.", ".kk....kk.", ".........."]),
                player_frame(["..dddd....", "...dd.....", "...dd.....", "...kk....."]),
                player_frame(["..dd..dd..", ".dd...dd..", ".kk....kk.", ".........."]),
            ],
            slime: [
                bake(&[
                    "....gggg....",
                    "..gggggggg..",
                    ".gggggggggg.",
                    ".ggwkggwkgg.",
                    "gggggggggggg",
                    "gggggggggggg",
                    "gGggggggggGg",
                    ".GGGGGGGGGG.",
                    "............",
                ]),
                bake(&[
                    "............",
                    "...gggggg...",
                    ".gggggggggg.",
                    "gggwkggwkggg",
                    "gggggggggggg",
                    "gggggggggggg",
                    "gGGggggggGGg",
                    "GGGGGGGGGGGG",
                    "............",
                ]),
            ],
            bat: [
                bake(&[
                    "pp........pp",
                    "ppp..pp..ppp",
                    "pppppppppppp",
                    ".ppprpprppp.",
                    "..pppppppp..",
                    "...pp..pp...",
                    "............",
                    "............",
                ]),
                bake(&[
                    "............",
                    ".....pp.....",
                    "..pppppppp..",
                    "pppprpprpppp",
                    "pp.pppppp.pp",
                    "p...pppp...p",
                    "............",
                    "............",
                ]),
            ],
            dummy: bake(&[
                "...wwww...",
                "..wrrrrw..",
                ".wrwwwwrw.",
                ".wrwrrwrw.",
                ".wrwrrwrw.",
                ".wrwwwwrw.",
                "..wrrrrw..",
                "...wwww...",
                "....nn....",
                "....nn....",
                "....nn....",
                "....nn....",
                "...nnnn...",
                "..nnnnnn..",
            ]),
            turret: bake(&[
                "....cccc....",
                "...cwwwwc...",
                "..cwwccwwc..",
                "..cwwccwwc..",
                "...cwwwwc...",
                "..MMccccMM..",
                ".MMMMMMMMMM.",
                ".MmmmmmmmmM.",
                "MMmmmmmmmmMM",
                "MMMMMMMMMMMM",
            ]),
            barrel: bake(&[
                "..NNNNNN..",
                ".NeeeeeeN.",
                "NeeeeeeeeN",
                "NNNNNNNNNN",
                "NeeeyyeeeN",
                "NeeyyyyeeN",
                "NeeeyyeeeN",
                "NeeeyyeeeN",
                "NNNNNNNNNN",
                "NeeeeeeeeN",
                ".NeeeeeeN.",
                "..NNNNNN..",
            ]),
            heart: bake(&[".rr.rr.", "rrrrrrr", "rrrrrrr", ".rrrrr.", "..rrr..", "...r..."]),
        }
    }
}

/// 画一张精灵（坐标取整，保证像素对齐）
pub fn spr(t: &Texture2D, x: f32, y: f32, flip: bool, tint: Color) {
    draw_texture_ex(
        t,
        x.round(),
        y.round(),
        tint,
        DrawTextureParams { flip_x: flip, ..Default::default() },
    );
}

pub fn rect(x: f32, y: f32, w: f32, h: f32, col: u32) {
    draw_rectangle(x.round(), y.round(), w, h, rgb(col));
}

pub fn rect_a(x: f32, y: f32, w: f32, h: f32, col: u32, a: f32) {
    draw_rectangle(x.round(), y.round(), w, h, rgba(col, a));
}

/// 横向进度条：底色 + 填充
pub fn bar(x: f32, y: f32, w: f32, h: f32, v: f32, col: u32) {
    rect(x - 1.0, y - 1.0, w + 2.0, h + 2.0, pal::INK);
    rect(x, y, w, h, 0x2a2238);
    let f = (w * v.clamp(0.0, 1.0)).round();
    if f > 0.0 {
        rect(x, y, f, h, col);
    }
}

struct TextCmd {
    x: f32,
    y: f32,
    size: f32,
    color: u32,
    alpha: f32,
    s: String,
    /// 0 左对齐 / 1 居中 / 2 右对齐
    align: u8,
}

pub struct Gfx {
    font: Option<Font>,
    /// 是否加载到了中文字体（否则界面文字退回英文）
    pub cn: bool,
    texts: Vec<TextCmd>,
    pub s: Sprites,
}

impl Gfx {
    pub fn new() -> Gfx {
        // 依次尝试系统自带的中文字体；都没有就用内置英文字体
        let mut font = None;
        let dir = std::env::var("WINDIR").unwrap_or_else(|_| "C:\\Windows".to_string());
        for name in ["simhei.ttf", "Deng.ttf", "msyh.ttc", "msyh.ttf"] {
            let path = std::path::Path::new(&dir).join("Fonts").join(name);
            if let Ok(bytes) = std::fs::read(&path) {
                if let Ok(f) = load_ttf_font_from_bytes(&bytes) {
                    font = Some(f);
                    break;
                }
            }
        }
        Gfx { cn: font.is_some(), font, texts: Vec::new(), s: Sprites::new() }
    }

    /// 按当前语言二选一
    pub fn t<'a>(&self, cn: &'a str, en: &'a str) -> &'a str {
        if self.cn {
            cn
        } else {
            en
        }
    }

    fn push(&mut self, x: f32, y: f32, size: f32, color: u32, alpha: f32, s: &str, align: u8) {
        if !s.is_empty() && alpha > 0.01 {
            self.texts.push(TextCmd { x, y, size, color, alpha, s: s.to_string(), align });
        }
    }

    /// 文字入队。坐标是 320x180 画布坐标，y 是基线；size 是画布像素高度。
    pub fn text(&mut self, x: f32, y: f32, size: f32, color: u32, s: &str) {
        self.push(x, y, size, color, 1.0, s, 0);
    }

    pub fn text_c(&mut self, x: f32, y: f32, size: f32, color: u32, s: &str) {
        self.push(x, y, size, color, 1.0, s, 1);
    }

    pub fn text_r(&mut self, x: f32, y: f32, size: f32, color: u32, s: &str) {
        self.push(x, y, size, color, 1.0, s, 2);
    }

    pub fn text_ca(&mut self, x: f32, y: f32, size: f32, color: u32, alpha: f32, s: &str) {
        self.push(x, y, size, color, alpha, s, 1);
    }

    /// 把入队的文字按屏幕分辨率画出来。scale = 画布放大倍数，(ox, oy) = 画布在屏幕上的左上角。
    pub fn flush(&mut self, scale: f32, ox: f32, oy: f32) {
        let font = self.font.as_ref();
        for c in self.texts.drain(..) {
            let fs = (c.size * scale).round().max(6.0) as u16;
            let mut x = ox + c.x * scale;
            let y = oy + c.y * scale;
            if c.align != 0 {
                let w = measure_text(&c.s, font, fs, 1.0).width;
                x -= if c.align == 1 { w / 2.0 } else { w };
            }
            let sh = (scale * 0.5).max(1.0);
            draw_text_ex(
                &c.s,
                x + sh,
                y + sh,
                TextParams { font, font_size: fs, color: rgba(pal::INK, c.alpha * 0.9), ..Default::default() },
            );
            draw_text_ex(
                &c.s,
                x,
                y,
                TextParams { font, font_size: fs, color: rgba(c.color, c.alpha), ..Default::default() },
            );
        }
    }
}
