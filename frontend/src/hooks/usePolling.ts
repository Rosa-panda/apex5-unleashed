// 标准形态轮询（ADR-029 F3）：挂载即调一次 fn，之后每 intervalMs 重复，卸载清理。
// 间隔以调用点字面量为准（各页 200ms~3s 各归各，禁止「顺手统一」）；
// deps 透传给 effect（依赖 [load] 的调用点原样保留）；catch 行为随 fn 自带。
import { useEffect } from 'react'

export function usePolling(fn: () => void, intervalMs: number, deps: unknown[] = []) {
  useEffect(() => {
    fn()
    const t = setInterval(fn, intervalMs)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}
