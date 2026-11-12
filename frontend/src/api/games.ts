// 游戏域（ADR-029 F1 自 api.ts 拆出）：游戏档案/Mod 管家/震动修复/联动开关
import { post } from './http'
import type { VibFixStatus } from './types'

export const games = {
  games: () => fetch('/api/games').then(r => r.json()),
  saveGame: (g: { name: string; exe: string[]; note: string }) => post('/api/games', g),
  deleteGame: (id: string) => fetch(`/api/games/${id}`, { method: 'DELETE' }).then(r => r.json()),
  applyGame: (id: string) => post(`/api/games/${id}/apply`),
  importConfig: (data: unknown) => post('/api/games/import-config', data) as Promise<{ ok: boolean; count: number; names: string[] }>,
  // 「另存为」框阻塞到用户点完：放宽超时，避免超时重试弹第二个框
  exportGame: (id: string) => post(`/api/games/${id}/export`, undefined, 600000) as Promise<{ ok: boolean; path?: string; cancelled?: boolean }>,
  modOpenDir: (gid: string) => post(`/api/mods/${gid}/open-dir`),
  arcadeLaunch: () => post('/api/arcade/launch'),
  setGameExe: (id: string, exe: string[]) => post(`/api/games/${id}/exe`, { exe }),
  setGameDisabled: (id: string, disabled: boolean) => post(`/api/games/${id}/disable`, { disabled }),
  importOfficial: () => post('/api/games/import-official'),
  officialSrc: () => fetch('/api/games/official-src').then(r => r.json()) as Promise<{ available: boolean; path: string; custom: string }>,
  setOfficialSrc: (path: string) => post('/api/games/official-src', { path }),
  // 系统选择框会阻塞到用户点完：放宽超时，否则 6s 超时重试会弹出第二个框
  pickOfficialSrc: () => post('/api/games/official-src/pick', undefined, 600000) as Promise<{ ok: boolean; path?: string; cancelled?: boolean }>,
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
  setFeedback: (enabled: boolean) => post('/api/feedback', { enabled }),
  vibfix: () => fetch('/api/vibfix').then(r => r.json()) as Promise<VibFixStatus>,
  vibfixSet: (enabled: boolean, mode: 'temporary' | 'permanent' = 'temporary') =>
    post('/api/vibfix/set', { enabled, mode }) as Promise<{
      ok: boolean; state: VibFixStatus['state']
    }>,
  vibfixAuto: (enabled: boolean) => post('/api/vibfix/auto', { enabled }) as Promise<{
    ok: boolean; auto: boolean
  }>,
}
