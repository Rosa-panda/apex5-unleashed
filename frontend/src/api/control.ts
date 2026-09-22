// 控制域（ADR-029 F1 自 api.ts 拆出）：扳机/马达/握把/紧急停止/占用回收
import { post } from './http'

export const control = {
  trigger: (side: string, mode: string, params: Record<string, number>, apply: boolean) =>
    post('/api/trigger', { side, mode, params, apply }),
  clearTrigger: (side: string) => post('/api/trigger/clear', { side }),
  rumble: (l: number, r: number, duration?: number) => post('/api/rumble', { l, r, duration }),
  grip: (side: string, params: Record<string, number>) => post('/api/grip', { side, params }),
  unbindGrip: (side: string) => post('/api/grip/unbind', { side, params: {} }),
  panic: () => post('/api/panic'),
  reclaim: () => post('/api/proxy/reclaim'),
}
