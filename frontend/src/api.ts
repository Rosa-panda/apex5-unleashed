// 后端 REST 封装（同源部署，走相对路径；dev 由 vite proxy）
export interface TriggerState { mode: string; params: Record<string, number>; source: string; applied_at: string }
export interface GripBindState { source?: string; applied_at?: string }
export interface EngineSnapshot {
  device: { kind: string | null; online: boolean; battery?: { level: number; charging: boolean } | null }
  state: {
    triggers: { left: TriggerState | null; right: TriggerState | null }
    rumble: { l: number; r: number; updated_at: string | null }
    gripBind: { left: GripBindState | null; right: GripBindState | null }
  }
  proxy: { holder: string; detail: string; since: string | null; mild?: boolean }
  events: EngineEvent[]
}
export interface EngineEvent { ts: string; kind: string; hist?: boolean; [k: string]: unknown }
// 游戏震动修复（飞智虚拟手柄抢 XInput 0 号槽）：absent=没装 / enabled=活跃会吞震动 / disabled=已禁用
export interface VibFixStatus {
  state: 'absent' | 'enabled' | 'disabled'
  service: string
  auto: boolean
  ledger: { mode: 'temporary' | 'permanent' | 'restore' | null; state: string | null; since: string | null;
    history: Array<{ ts: string; action: string; state: string }> }
}
export interface Preset {
  id: string; name: string; note: string; builtin: boolean
  actions: Array<Record<string, unknown>>; saved_at?: string
}

async function post(url: string, body?: unknown) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  const j = await r.json().catch(() => ({}))
  if (!r.ok || j.error) throw new Error(j.error ?? `${r.status}`)
  return j
}

// GET 同款守门：后端 400 会带 {error}，不抛的话错误对象会灌进 state 炸渲染
// （体验区面板「展不开」的根因，2026-09-20）
async function get(url: string) {
  const r = await fetch(url)
  const j = await r.json().catch(() => ({}))
  if (!r.ok || j.error) throw new Error(j.error ?? `${r.status}`)
  return j
}

export const api = {
  uiError: (msg: string, stack: string, where: string) =>
    fetch('/api/ui-error', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ msg, stack, where }),
    }).catch(() => {}),
  state: () => fetch('/api/state').then(r => r.json()) as Promise<EngineSnapshot>,
  modes: () => fetch('/api/modes').then(r => r.json()),
  presets: () => fetch('/api/presets').then(r => r.json()) as Promise<{ builtin: Preset[]; user: Preset[] }>,
  trigger: (side: string, mode: string, params: Record<string, number>, apply: boolean) =>
    post('/api/trigger', { side, mode, params, apply }),
  clearTrigger: (side: string) => post('/api/trigger/clear', { side }),
  rumble: (l: number, r: number, duration?: number) => post('/api/rumble', { l, r, duration }),
  grip: (side: string, params: Record<string, number>) => post('/api/grip', { side, params }),
  unbindGrip: (side: string) => post('/api/grip/unbind', { side, params: {} }),
  panic: () => post('/api/panic'),
  reclaim: () => post('/api/proxy/reclaim'),
  pulse: () => post('/api/test/pulse'),
  sine: (seconds: number, freq: number, amp: number) => post('/api/test/sine', { seconds, freq, amp }),
  applyPreset: (id: string) => post(`/api/presets/${id}/apply`),
  savePreset: (name: string, note: string, actions: Array<Record<string, unknown>>) =>
    post('/api/presets', { name, note, actions }),
  deletePreset: (id: string) => fetch(`/api/presets/${id}`, { method: 'DELETE' }).then(r => r.json()),
  games: () => fetch('/api/games').then(r => r.json()),
  saveGame: (g: { name: string; exe: string[]; preset_id: string; note: string }) => post('/api/games', g),
  deleteGame: (id: string) => fetch(`/api/games/${id}`, { method: 'DELETE' }).then(r => r.json()),
  applyGame: (id: string) => post(`/api/games/${id}/apply`),
  linkGame: (id: string, preset_id: string) => post(`/api/games/${id}/link`, { preset_id }),
  setGameExe: (id: string, exe: string[]) => post(`/api/games/${id}/exe`, { exe }),
  importOfficial: () => post('/api/games/import-official'),
  officialSrc: () => fetch('/api/games/official-src').then(r => r.json()) as Promise<{ available: boolean; path: string }>,
  mods: () => fetch('/api/mods').then(r => r.json()) as Promise<{
    mods: Array<{ gid: string; name: string; mod_name: string; version: string; start_type: number;
      installed: boolean; enabled: boolean; installing: boolean; running: boolean }>
    active_gid: string | null
    ingress: { enabled: boolean; port: number | null; error: string; packets: number;
      applied: number; ignored: number; last_packet_at: string | null } | null
  }>,
  modInstall: (gid: string) => post(`/api/mods/${gid}/install`),
  modUninstall: (gid: string) => post(`/api/mods/${gid}/uninstall`),
  modEnable: (gid: string, enabled: boolean) => post(`/api/mods/${gid}/enable`, { enabled }),
  modStop: () => post('/api/mods/stop'),
  setUniversalVib: (enabled: boolean) => post('/api/vib/universal', { enabled }),
  setAutoswitch: (enabled: boolean) => post('/api/autoswitch', { enabled }),
  vibfix: () => fetch('/api/vibfix').then(r => r.json()) as Promise<VibFixStatus>,
  vibfixSet: (enabled: boolean, mode: 'temporary' | 'permanent' = 'temporary') =>
    post('/api/vibfix/set', { enabled, mode }) as Promise<{
      ok: boolean; state: VibFixStatus['state']
    }>,
  vibfixAuto: (enabled: boolean) => post('/api/vibfix/auto', { enabled }) as Promise<{
    ok: boolean; auto: boolean
  }>,
  autostart: () => fetch('/api/settings/autostart').then(r => r.json()) as Promise<{
    ok: boolean; enabled: boolean; command: string
  }>,
  setAutostart: (enabled: boolean) => post('/api/settings/autostart', { enabled }) as Promise<{
    ok: boolean; enabled: boolean; command?: string; error?: string
  }>,
  imgCacheStatus: () => fetch('/api/imgcache/status').then(r => r.json()) as Promise<{
    ok: boolean; count: number; bytes: number
  }>,
  imgCacheClear: () => post('/api/imgcache/clear') as Promise<{ ok: boolean; freed_bytes: number }>,
  openDataFolder: () => post('/api/open-folder', {}),
  attrib: () => post('/api/test/attrib'),
  extKeys: () => fetch('/api/extkeys').then(r => r.json()) as Promise<{
    ok: boolean; keys: Array<{ name: string; target: number; target_name: string; turbo: number; freq: number }>
  }>,
  extKeysTestMode: (on: boolean) => post('/api/extkeys/testmode', { on }) as Promise<{
    ok: boolean; version: number; mapping?: Array<{ name: string; target_name: string }>
  }>,
  ledTest: (r: number, g: number, b: number) => post('/api/led/test', { r, g, b }),
  ledConfig: () => fetch('/api/led/config').then(r => r.json()) as Promise<{ ok: boolean; bean: LedBean | null }>,
  ledApply: (mode: string, colors: number[][], brightness?: number, period?: number) =>
    post('/api/led/apply', { mode, colors, brightness, period }),
  ledBackup: () => post('/api/led/backup'),
  ledRestore: () => post('/api/led/restore'),

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

  // 宏（ADR-021：板载宏）
  macroConfig: () => fetch('/api/macro/config').then(r => r.json()) as Promise<{
    cfg: number; version: number; macros: Macro[]
  }>,
  macroWrite: (macros: Macro[], unbind: string[] = []) =>
    post('/api/macro/write', { macros, unbind }) as Promise<{
      ok: boolean; cfg: number; version: number; warnings: string[]
    }>,
  macroRecordStart: () => post('/api/macro/record/start'),
  macroRecordStop: () => post('/api/macro/record/stop') as Promise<{
    ok: boolean; actions: MacroAction[]; seconds: number
  }>,
  macroRecordStatus: () => fetch('/api/macro/record/status').then(r => r.json()) as Promise<{
    recording: boolean; steps: number; seconds: number
  }>,
  macroBackup: () => post('/api/macro/backup') as Promise<{ ok: boolean; path: string; macros: number }>,
  macroRestore: () => post('/api/macro/restore') as Promise<{ ok: boolean; warnings?: string[] }>,

  // 体验区（ADR-026：隐藏功能孵化区）
  expList: () => fetch('/api/exp').then(r => r.json()) as Promise<ExpList>,
  expVerdict: (id: string, verdict: 'good' | 'bad' | 'pending', note = '') =>
    post('/api/exp/verdict', { id, verdict, note }) as Promise<{
      ok: boolean; id: string; verdict: string; ts: number; summary: ExpSummary
    }>,

  // 体验区功能端点（ADR-027）
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
  expGyro: () => get('/api/exp/gyro') as Promise<any>,
  expGyroSet: (patch: Record<string, unknown>) => post('/api/exp/gyro', { patch }) as Promise<any>,
  expStickMap: () => get('/api/exp/stickmap') as Promise<any>,
  expStickMapSet: (patch: Record<string, unknown>) => post('/api/exp/stickmap', { patch }) as Promise<any>,
  expRgb: () => get('/api/exp/rgbbridge') as Promise<any>,
  expRgbSet: (enabled: boolean, port = 7878) => post('/api/exp/rgbbridge', { enabled, port }) as Promise<any>,
  expRgbTest: (rgb: number[]) => post('/api/exp/rgbbridge/test', { rgb }) as Promise<any>,
  expRgbFlash: (enabled: boolean, rgb: number[]) => post('/api/exp/rgbbridge/flash', { enabled, rgb }) as Promise<any>,
  expDiag: (op: string, body: Record<string, unknown> = {}) =>
    post('/api/exp/diagnostics', { op, ...body }) as Promise<any>,
  expDiagData: () => get('/api/exp/diagnostics') as Promise<any>,
  expShareEncode: (kind = 'profile', blob_hex = '') =>
    post('/api/exp/sharecode/encode', { kind, blob_hex }) as Promise<any>,
  expShareDecode: (code: string) => post('/api/exp/sharecode/decode', { code }) as Promise<any>,
  expShareApply: (code: string) => post('/api/exp/sharecode/apply', { code }) as Promise<any>,
}

export interface ExpFeature {
  id: string; tier: 1 | 2 | 3; plan: string; title: string; desc: string
  enabled: boolean; tierLabel: string; verdict: 'good' | 'bad' | 'pending'; note: string
}
export interface ExpSummary { good: number; bad: number; pending: number }
export interface ExpList { ok: boolean; features: ExpFeature[]; summary: ExpSummary }
export interface MacroAction { t: number; key: number; ev: number }
export interface Macro {
  key_id: number; type: number; interval: number; actions: MacroAction[]
}
export interface LedBean {
  version: number; click_feedback: number; loop_start: number; loop_end: number
  loop_time: number; brightness: number; rgb_num: number; led_mode: number; grip_sync: number | null
}
