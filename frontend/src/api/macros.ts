// 宏/拓展键域（ADR-029 F1 自 api.ts 拆出；宏 ADR-021）
import { post } from './http'
import type { Macro, MacroAction } from './types'

export const macros = {
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
  extKeys: () => fetch('/api/extkeys').then(r => r.json()) as Promise<{
    ok: boolean; keys: Array<{ name: string; target: number; target_name: string; turbo: number; freq: number }>
  }>,
  extKeysTestMode: (on: boolean) => post('/api/extkeys/testmode', { on }) as Promise<{
    ok: boolean; version: number; mapping?: Array<{ name: string; target_name: string }>
  }>,
}
