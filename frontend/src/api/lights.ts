// 灯光域（ADR-029 F1 自 api.ts 拆出）
import { post } from './http'
import type { LedBean, LedDetect } from './types'

export const lights = {
  ledTest: (r: number, g: number, b: number) => post('/api/led/test', { r, g, b }),
  ledConfig: () => fetch('/api/led/config').then(r => r.json()) as Promise<{
    ok: boolean; bean: LedBean | null
    detect?: LedDetect | null      // 帧表反推的当前灯效（mode/colors/known）
    frames_b64?: string            // 设备当前帧表原文（进页还原预览用）
  }>,
  ledApply: (mode: string, colors: number[][], brightness?: number, period?: number,
    params?: Record<string, unknown>) =>
    post('/api/led/apply', { mode, colors, brightness, period, params: params ?? {} }),
  ledApplyFrames: (bean: LedBean, framesB64: string) =>
    post('/api/led/apply_frames', { bean, frames_b64: framesB64 }),
  ledBackup: () => post('/api/led/backup'),
  ledRestore: () => post('/api/led/restore'),
}
