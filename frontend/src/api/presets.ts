// 预设域（ADR-029 F1 自 api.ts 拆出）
import { post } from './http'
import type { Preset } from './types'

export const presets = {
  presets: () => fetch('/api/presets').then(r => r.json()) as Promise<{ builtin: Preset[]; user: Preset[] }>,
  applyPreset: (id: string) => post(`/api/presets/${id}/apply`),
  savePreset: (name: string, note: string, actions: Array<Record<string, unknown>>) =>
    post('/api/presets', { name, note, actions }),
  deletePreset: (id: string) => fetch(`/api/presets/${id}`, { method: 'DELETE' }).then(r => r.json()),
}
