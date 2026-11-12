//! 扳机猎人（Trigger Ranger）—— Apex5 Unleashed 内置的像素横版演示游戏。
//! 目的：把手柄的自适应扳机和震动放进真实的游戏场景里感受和调校。
//!
//! 模块：
//! - `feel`  扳机（DSX → 工具 → 手柄）与震动（XInput）的出口
//! - `tune`  全部手感参数：来自档案里的 `feel` 配置，可导出 / 导入 / F5 热重载
//! - `pad`   手柄 / 键盘输入
//! - `game`  世界、武器、敌人、绘制
//! - `level` 关卡地形与布置
//! - `gfx` / `sfx`  像素精灵、文字、合成音效
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod cfg;
mod feel;
mod game;
mod gfx;
mod level;
mod pad;
mod sfx;
mod tune;

use cfg::Cfg;
use feel::{Dsx, Rumble, L, R};
use game::{draw_backdrop, Fx, Hud, World};
use gfx::*;
use macroquad::prelude::*;
use pad::{Input, Pad};
use sfx::{Sfx, S};

/// 低分辨率画布贴到屏幕时是否上下翻转（macroquad 的渲染目标是倒着存的）。
/// 如果画面整体上下颠倒，把它改成 false。
const FLIP_Y: bool = true;

fn conf() -> Conf {
    Conf {
        window_title: "Trigger Ranger - Apex5 Unleashed".to_owned(),
        window_width: 1280,
        window_height: 720,
        high_dpi: true,
        ..Default::default()
    }
}

#[derive(Clone, Copy, PartialEq)]
enum Scene {
    Title,
    Play,
    Pause,
    /// 参数：是否从暂停菜单进入（决定返回去哪）
    Settings(bool),
    Win,
}

fn apply_cfg(c: &Cfg, dsx: &mut Dsx, rum: &mut Rumble, sfx: &mut Sfx) {
    rum.scale = c.rumble as f32 / 10.0;
    dsx.scale = c.trigger as f32 / 10.0;
    dsx.enabled = c.trigger > 0;
    sfx.vol = c.volume as f32 / 10.0;
}

/// 菜单上下移动选中项
fn nav(sel: &mut usize, n: usize, inp: &Input, sfx: &Sfx) {
    if inp.menu_y != 0 && n > 0 {
        *sel = ((*sel as i32 + inp.menu_y).rem_euclid(n as i32)) as usize;
        sfx.play(S::Ui);
    }
}

fn draw_menu(g: &mut Gfx, items: &[String], sel: usize, y: f32) {
    for (i, it) in items.iter().enumerate() {
        let on = i == sel;
        let s = if on { format!("> {} <", it) } else { it.clone() };
        g.text_c(VW / 2.0, y + i as f32 * 13.0, 8.0, if on { pal::YELLOW } else { pal::GRAY }, &s);
    }
}

fn dots(v: i32) -> String {
    let v = v.clamp(0, 10) as usize;
    format!("{}{} {}", "■".repeat(v), "□".repeat(10 - v), v * 10)
}

fn settings_items(g: &Gfx, c: &Cfg) -> Vec<String> {
    let onoff = |b: bool| if b { g.t("开", "ON") } else { g.t("关", "OFF") };
    let level = |v: i32| if g.cn { dots(v) } else { format!("{}%", v * 10) };
    vec![
        format!("{}  {}", g.t("震动强度", "RUMBLE"), level(c.rumble)),
        format!("{}  {}", g.t("扳机强度", "TRIGGER"), level(c.trigger)),
        format!("{}  {}", g.t("音量", "VOLUME"), level(c.volume)),
        format!("{}  {}", g.t("全屏", "FULLSCREEN"), onoff(c.fullscreen)),
        format!("{}  {}", g.t("手感面板", "FEEL PANEL"), onoff(c.detail)),
        g.t("返回", "BACK").to_string(),
    ]
}

fn main() {
    // `apex5-arcade.exe --dump-feel <文件>`：把默认手感配置（`feel` 段）写到文件后退出，
    // 不开窗口。内置游戏档案里的 `feel` 就是用它生成的。
    let args: Vec<String> = std::env::args().collect();
    if let Some(i) = args.iter().position(|a| a == "--dump-feel") {
        if let Some(path) = args.get(i + 1) {
            let _ = std::fs::write(path, tune::default_json());
        }
        return;
    }
    // `--show-feel <文件>`：读取档案里的 `feel` 后，把「实际生效的配置 + 来源」写到文件并退出，
    // 用来确认导入的手感配置真的被游戏读到了。
    if let Some(i) = args.iter().position(|a| a == "--show-feel") {
        if let Some(path) = args.get(i + 1) {
            let info = tune::load();
            let body = format!(
                "{{\n  \"source\": {:?},\n  \"error\": {:?},\n  \"feel\": {}\n}}\n",
                info.source,
                info.error.unwrap_or_default(),
                tune::effective_json()
            );
            let _ = std::fs::write(path, body);
        }
        return;
    }
    macroquad::Window::from_config(conf(), game());
}

async fn game() {
    // 中文字体解析要一小会儿：先出一帧加载提示
    clear_background(BLACK);
    draw_text("LOADING...", 40.0, 60.0, 32.0, WHITE);
    next_frame().await;

    let mut feel_info = tune::load();
    let mut note_t = 0.0f32; // 顶部提示条剩余秒数（F5 重载结果）
    let mut gfx = Gfx::new();
    let mut sfx = Sfx::new().await;
    let mut cfg = Cfg::load();
    let mut pad = Pad::new();
    let mut dsx = Dsx::new();
    let mut rum = Rumble::new();
    apply_cfg(&cfg, &mut dsx, &mut rum, &mut sfx);
    if cfg.fullscreen {
        set_fullscreen(true);
    }

    let canvas = render_target(VW as u32, VH as u32);
    canvas.texture.set_filter(FilterMode::Nearest);
    let mut canvas_cam = Camera2D::from_display_rect(Rect::new(0.0, 0.0, VW, VH));
    canvas_cam.render_target = Some(canvas.clone());

    let mut world = World::new();
    let mut scene = Scene::Title;
    let mut sel = 0usize;
    let mut title_t = 0.0f32;
    prevent_quit();

    loop {
        if is_quit_requested() {
            break;
        }
        let dt = get_frame_time().min(1.0 / 30.0);
        let now = get_time();
        let inp = pad.poll(dt);
        title_t += dt;
        note_t = (note_t - dt).max(0.0);
        if inp.reload_cfg {
            feel_info = tune::load();
            note_t = 3.0;
        }
        if inp.debug {
            cfg.detail = !cfg.detail;
            cfg.save();
        }

        // ── 更新 ──
        let mut quit = false;
        match scene {
            Scene::Title => {
                dsx.relax();
                sfx.jet(0.0);
                nav(&mut sel, 3, &inp, &sfx);
                if inp.confirm {
                    sfx.play(S::UiOk);
                    match sel {
                        0 => {
                            world = World::new();
                            scene = Scene::Play;
                        }
                        1 => {
                            scene = Scene::Settings(false);
                            sel = 0;
                        }
                        _ => quit = true,
                    }
                }
            }
            Scene::Play => {
                let mut fx = Fx { dsx: &mut dsx, rum: &mut rum, sfx: &mut sfx };
                world.update(&inp, dt, &mut fx);
                if world.won {
                    scene = Scene::Win;
                    rum.stop();
                } else if inp.pause {
                    scene = Scene::Pause;
                    sel = 0;
                    rum.stop();
                    dsx.relax();
                    sfx.jet(0.0);
                }
            }
            Scene::Pause => {
                dsx.relax();
                nav(&mut sel, 4, &inp, &sfx);
                if inp.back || inp.pause {
                    scene = Scene::Play;
                } else if inp.confirm {
                    sfx.play(S::UiOk);
                    match sel {
                        0 => scene = Scene::Play,
                        1 => {
                            world.respawn();
                            scene = Scene::Play;
                        }
                        2 => {
                            scene = Scene::Settings(true);
                            sel = 0;
                        }
                        _ => {
                            scene = Scene::Title;
                            sel = 0;
                        }
                    }
                }
            }
            Scene::Settings(from_pause) => {
                dsx.relax();
                nav(&mut sel, 6, &inp, &sfx);
                let step = if inp.menu_x != 0 {
                    inp.menu_x
                } else if inp.confirm && sel < 5 {
                    1
                } else {
                    0
                };
                if step != 0 {
                    match sel {
                        0 => {
                            cfg.rumble = (cfg.rumble + step).clamp(0, 10);
                            apply_cfg(&cfg, &mut dsx, &mut rum, &mut sfx);
                            rum.hit(tune::test()); // 调完立刻震一下，当场感受
                        }
                        1 => {
                            cfg.trigger = (cfg.trigger + step).clamp(0, 10);
                            apply_cfg(&cfg, &mut dsx, &mut rum, &mut sfx);
                            dsx.kick_both(tune::shock(), 0.5);
                        }
                        2 => {
                            cfg.volume = (cfg.volume + step).clamp(0, 10);
                            apply_cfg(&cfg, &mut dsx, &mut rum, &mut sfx);
                            sfx.play(S::UiOk);
                        }
                        3 => {
                            cfg.fullscreen = !cfg.fullscreen;
                            set_fullscreen(cfg.fullscreen);
                        }
                        4 => cfg.detail = !cfg.detail,
                        _ => {}
                    }
                    cfg.save();
                }
                if inp.back || (inp.confirm && sel == 5) {
                    sfx.play(S::UiOk);
                    scene = if from_pause { Scene::Pause } else { Scene::Title };
                    sel = 0;
                }
            }
            Scene::Win => {
                dsx.relax();
                sfx.jet(0.0);
                if inp.confirm {
                    sfx.play(S::UiOk);
                    scene = Scene::Title;
                    sel = 0;
                }
            }
        }
        if quit {
            break;
        }

        // ── 手感输出 ──
        dsx.update(dt, now);
        let (lo, hi) = rum.update(dt);
        pad.rumble(lo, hi, now);

        // ── 绘制到低分辨率画布 ──
        let hud = Hud {
            lt: inp.lt,
            rt: inp.rt,
            trig: [dsx.effective(L), dsx.effective(R)],
            rum: rum.out,
            port: dsx.port,
            port_found: dsx.port_found,
            packets: dsx.packets,
            pads: pad.connected(),
            detail: cfg.detail,
        };
        set_camera(&canvas_cam);
        clear_background(BLACK);
        match scene {
            Scene::Title => {
                draw_backdrop(title_t, title_t * 18.0);
                rect(0.0, VH - 22.0, VW, 22.0, pal::ROCK);
                rect(0.0, VH - 22.0, VW, 2.0, pal::DGREEN);
                rect(0.0, VH - 22.0, VW, 1.0, pal::GREEN);
                let frame = 1 + ((title_t * 10.0) as usize % 2);
                spr(&gfx.s.player[frame], 60.0, VH - 36.0, false, WHITE);
                spr(&gfx.s.slime[(title_t * 3.0) as usize % 2], 230.0, VH - 31.0, true, WHITE);
                let title = gfx.t("扳机猎人", "TRIGGER RANGER").to_string();
                gfx.text_c(VW / 2.0, 52.0, 26.0, pal::YELLOW, &title);
                let sub = gfx.t("TRIGGER RANGER · Apex5 Unleashed 内置演示", "Apex5 Unleashed built-in demo").to_string();
                gfx.text_c(VW / 2.0, 66.0, 6.5, pal::GRAY, &sub);
                let items = vec![
                    gfx.t("开始游戏", "START").to_string(),
                    gfx.t("设置", "SETTINGS").to_string(),
                    gfx.t("退出", "QUIT").to_string(),
                ];
                draw_menu(&mut gfx, &items, sel, 92.0);
                let status = if hud.pads > 0 {
                    format!("{} x{}  ·  DSX :{}", gfx.t("手柄已连接", "Pad connected"), hud.pads, hud.port)
                } else {
                    gfx.t("未检测到手柄 · 键盘：A/D 移动 空格跳 J 射击 K 背包 Q/E 换武器 R 装弹", "No pad · Keys: A/D move, Space jump, J fire, K jetpack, Q/E weapon, R reload").to_string()
                };
                gfx.text_c(VW / 2.0, 140.0, 5.5, pal::DGRAY, &status);
                let hint = gfx.t("扳机效果需要 Apex5 Unleashed 在后台运行", "Trigger effects need Apex5 Unleashed running").to_string();
                gfx.text_c(VW / 2.0, 149.0, 5.5, pal::DGRAY, &hint);
                let feel_line = format!("{}：{}  ·  F5 {}", gfx.t("手感配置", "Feel config"), feel_info.source, gfx.t("重新读取", "reload"));
                gfx.text_c(VW / 2.0, 158.0, 5.5, pal::DGRAY, &feel_line);
            }
            Scene::Play => world.draw(&mut gfx, &hud),
            Scene::Pause | Scene::Settings(true) => {
                world.draw(&mut gfx, &hud);
                rect_a(0.0, 0.0, VW, VH, pal::INK, 0.72);
            }
            Scene::Settings(false) => {
                draw_backdrop(title_t, title_t * 18.0);
                rect_a(0.0, 0.0, VW, VH, pal::INK, 0.5);
            }
            Scene::Win => {
                draw_backdrop(title_t, title_t * 18.0);
                let s = &world.stats;
                let title = gfx.t("通关！", "CLEARED!").to_string();
                gfx.text_c(VW / 2.0, 46.0, 22.0, pal::YELLOW, &title);
                let (m, sec) = ((s.time / 60.0) as u32, (s.time % 60.0) as u32);
                let lines = [
                    format!("{}  {}:{:02}", gfx.t("用时", "TIME"), m, sec),
                    format!("{}  {}", gfx.t("击杀", "KILLS"), s.kills),
                    format!("{}  {}%", gfx.t("命中率", "ACCURACY"), world.accuracy()),
                    format!("{}  {}", gfx.t("倒下次数", "DEATHS"), s.deaths),
                ];
                for (i, l) in lines.iter().enumerate() {
                    gfx.text_c(VW / 2.0, 72.0 + i as f32 * 13.0, 8.0, pal::WHITE, l);
                }
                let hint = gfx.t("A / 回车 返回标题", "A / Enter: back to title").to_string();
                gfx.text_c(VW / 2.0, 150.0, 6.0, pal::GRAY, &hint);
            }
        }
        // 菜单文字叠在最上层
        match scene {
            Scene::Pause => {
                let title = gfx.t("暂停", "PAUSED").to_string();
                gfx.text_c(VW / 2.0, 50.0, 16.0, pal::WHITE, &title);
                let items = vec![
                    gfx.t("继续", "RESUME").to_string(),
                    gfx.t("回到存档点", "BACK TO CHECKPOINT").to_string(),
                    gfx.t("设置", "SETTINGS").to_string(),
                    gfx.t("返回标题", "QUIT TO TITLE").to_string(),
                ];
                draw_menu(&mut gfx, &items, sel, 78.0);
            }
            Scene::Settings(_) => {
                let title = gfx.t("设置", "SETTINGS").to_string();
                gfx.text_c(VW / 2.0, 40.0, 14.0, pal::WHITE, &title);
                let items = settings_items(&gfx, &cfg);
                draw_menu(&mut gfx, &items, sel, 64.0);
                let hint = gfx.t("左右调节 · 调震动/扳机时会当场试一下", "Left/Right to adjust · rumble/trigger changes fire a test pulse").to_string();
                gfx.text_c(VW / 2.0, 156.0, 5.5, pal::DGRAY, &hint);
            }
            _ => {}
        }
        // F5 重载手感配置后的结果提示（任何画面都显示几秒）
        if note_t > 0.0 {
            let (txt, col) = match &feel_info.error {
                Some(e) => (format!("{}：{}", gfx.t("手感配置有误，已改用默认", "Bad feel config, using defaults"), e), pal::RED),
                None => (format!("{}：{}", gfx.t("已载入手感配置", "Feel config loaded"), feel_info.source), pal::GREEN),
            };
            gfx.text_ca(VW / 2.0, 11.0, 6.5, col, note_t.min(1.0), &txt);
        }

        // ── 画布整数倍放大贴到屏幕，再按屏幕分辨率画文字 ──
        set_default_camera();
        clear_background(BLACK);
        let (sw, sh) = (screen_width(), screen_height());
        let mut scale = (sw / VW).min(sh / VH);
        if scale >= 1.0 {
            scale = scale.floor();
        }
        let (dw, dh) = (VW * scale, VH * scale);
        let (ox, oy) = (((sw - dw) / 2.0).floor(), ((sh - dh) / 2.0).floor());
        draw_texture_ex(
            &canvas.texture,
            ox,
            oy,
            WHITE,
            DrawTextureParams { dest_size: Some(vec2(dw, dh)), flip_y: FLIP_Y, ..Default::default() },
        );
        gfx.flush(scale, ox, oy);
        next_frame().await;
    }

    // 退出：停震、扳机还原
    pad.rumble_off();
    dsx.shutdown();
    cfg.save();
}
