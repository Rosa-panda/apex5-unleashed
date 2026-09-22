// 体验区域（ADR-029 F1 自 api.ts 拆出；ADR-026 注册表/判定 + ADR-027 非体感功能端点）
import { get, post } from './http'
import type { ExpList, ExpSummary } from './types'

export const exp = {
  expList: () => fetch('/api/exp').then(r => r.json()) as Promise<ExpList>,
  expVerdict: (id: string, verdict: 'good' | 'bad' | 'pending', note = '') =>
    post('/api/exp/verdict', { id, verdict, note }) as Promise<{
      ok: boolean; id: string; verdict: string; ts: number; summary: ExpSummary
    }>,
  expProfile: () => get('/api/exp/profile') as Promise<any>,
  expTurbo: (kid: number, mode: number, freq = 10) =>
    post('/api/exp/profile/turbo', { kid, mode, freq }) as Promise<any>,
  expStick: (side: string, body: Record<string, unknown>) =>
    post('/api/exp/profile/stick', { side, ...body }) as Promise<any>,
  expTriggerCurve: (side: string, zero: number, end: number) =>
    post('/api/exp/profile/trigger-curve', { side, zero, end }) as Promise<any>,
  expMotion: (body: Record<string, unknown>) =>
    post('/api/exp/profile/motion', body) as Promise<any>,
  expGripVib: (enabled: boolean, left: object, right: object) =>
    post('/api/exp/profile/gripvib', { enabled, left, right }) as Promise<any>,
  expTitle: (title: string) => post('/api/exp/profile/title', { title }) as Promise<any>,
  expSwitchSync: (slot: number) => post('/api/exp/profile/switch', { slot }) as Promise<any>,
  expSlots: () => get('/api/exp/slots') as Promise<any>,
  expSlotApply: (slot: number) => post('/api/exp/slots/apply', { slot }) as Promise<any>,
  expFactorySlot: (slot: number, confirm: string) =>
    post('/api/exp/factoryreset/slot', { slot, confirm }) as Promise<any>,
  expFactoryAll: (confirm: string) => post('/api/exp/factoryreset/all', { confirm }) as Promise<any>,
  expDevCfg: () => get('/api/exp/devcfg') as Promise<any>,
  expSetting: (op: string, body: Record<string, unknown> = {}) =>
    post('/api/exp/devcfg/setting', { op, ...body }) as Promise<any>,
  expNickname: (name: string) => post('/api/exp/devcfg/nickname', { name }) as Promise<any>,
  expReboot: () => post('/api/exp/devcfg/reboot') as Promise<any>,
  expOwner: () => get('/api/exp/owner') as Promise<any>,
  expAcquire: () => post('/api/exp/owner/acquire') as Promise<any>,
  expDiag: (op: string, body: Record<string, unknown> = {}) =>
    post('/api/exp/diagnostics', { op, ...body }) as Promise<any>,
  expDiagData: () => get('/api/exp/diagnostics') as Promise<any>,
  expShareEncode: (kind = 'profile', blob_hex = '') =>
    post('/api/exp/sharecode/encode', { kind, blob_hex }) as Promise<any>,
  expShareDecode: (code: string) => post('/api/exp/sharecode/decode', { code }) as Promise<any>,
  expShareApply: (code: string) => post('/api/exp/sharecode/apply', { code }) as Promise<any>,
}
