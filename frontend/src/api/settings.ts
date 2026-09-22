// 设置域（ADR-029 F1 自 api.ts 拆出）：开机自启/封面缓存/数据目录
import { post } from './http'

export const settings = {
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
}
