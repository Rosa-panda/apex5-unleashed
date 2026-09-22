// 屏幕域（ADR-029 F1 自 api.ts 拆出）
import { post } from './http'

export const screen = {
  screenConvert: (dataB64: string, name: string, mode = 'fill', targetFrames = 30) =>
    post('/api/screen/convert', { data_b64: dataB64, name, mode, target_frames: targetFrames }) as Promise<{
      ok: boolean; frames: number; interval_ms: number; total_frames: number; truncated: boolean; seconds: number
    }>,
  screenFlash: (confirm: boolean, restoreDefault = false) =>
    post('/api/screen/flash', { confirm, restore_default: restoreDefault }) as Promise<{
      ok: boolean; frames: number; seconds: number
    }>,
  screenFlags: () => fetch('/api/screen/flags').then(r => r.json()) as Promise<{
    ok: boolean; animation_on: boolean; status_bar: boolean
  }>,
  screenAnimation: (on: boolean) => post('/api/screen/animation', { on }) as Promise<{
    ok: boolean; animation_on: boolean; status_bar: boolean
  }>,
  screenStatusBar: (on: boolean) => post('/api/screen/statusbar', { on }) as Promise<{
    ok: boolean; animation_on: boolean; status_bar: boolean
  }>,
}
