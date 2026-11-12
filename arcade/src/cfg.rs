//! 设置的读写：`%APPDATA%\Apex5Unleashed\arcade.cfg`，每行一个 `键=值`。
use std::path::PathBuf;

pub struct Cfg {
    /// 震动强度 0..=10
    pub rumble: i32,
    /// 扳机强度 0..=10（0 = 关闭扳机效果）
    pub trigger: i32,
    /// 音量 0..=10
    pub volume: i32,
    pub fullscreen: bool,
    /// 是否显示手感面板
    pub detail: bool,
}

fn path() -> PathBuf {
    let base = std::env::var("APPDATA").unwrap_or_else(|_| ".".to_string());
    PathBuf::from(base).join("Apex5Unleashed").join("arcade.cfg")
}

impl Cfg {
    pub fn load() -> Cfg {
        let mut c = Cfg { rumble: 10, trigger: 10, volume: 7, fullscreen: false, detail: true };
        if let Ok(s) = std::fs::read_to_string(path()) {
            for line in s.lines() {
                let Some((k, v)) = line.split_once('=') else {
                    continue;
                };
                let n = v.trim().parse::<i32>().unwrap_or(0);
                match k.trim() {
                    "rumble" => c.rumble = n.clamp(0, 10),
                    "trigger" => c.trigger = n.clamp(0, 10),
                    "volume" => c.volume = n.clamp(0, 10),
                    "fullscreen" => c.fullscreen = n != 0,
                    "detail" => c.detail = n != 0,
                    _ => {}
                }
            }
        }
        c
    }

    pub fn save(&self) {
        let p = path();
        if let Some(dir) = p.parent() {
            let _ = std::fs::create_dir_all(dir);
        }
        let s = format!(
            "rumble={}\ntrigger={}\nvolume={}\nfullscreen={}\ndetail={}\n",
            self.rumble, self.trigger, self.volume, self.fullscreen as i32, self.detail as i32
        );
        let _ = std::fs::write(p, s);
    }
}
