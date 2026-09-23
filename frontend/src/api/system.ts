// 系统域（ADR-029 F1 自 api.ts 拆出）：UI 错误上报/快照/模式/测试台
import { post } from './http'
import type { EngineSnapshot } from './types'

export const system = {
  version: () =>
    fetch('/api/version').then(r => r.json()) as Promise<{ version: string; sha: string }>,
  uiError: (msg: string, stack: string, where: string) =>
    fetch('/api/ui-error', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ msg, stack, where }),
    }).catch(() => {}),
  state: () => fetch('/api/state').then(r => r.json()) as Promise<EngineSnapshot>,
  modes: () => fetch('/api/modes').then(r => r.json()),
  attrib: () => post('/api/test/attrib'),
  pulse: () => post('/api/test/pulse'),
  sine: (seconds: number, freq: number, amp: number) => post('/api/test/sine', { seconds, freq, amp }),
}
