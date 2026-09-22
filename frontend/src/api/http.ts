// HTTP 帮手（ADR-029 F1 自 api.ts 拆出，逐字搬迁）
export async function post(url: string, body?: unknown, timeout_ms = 6000) {
  // WebView2 偶发 POST 挂死（半死系统代理/半开连接池：GET 能过、带 body 的 POST
  // 永不返回，2026-09-21 用户实测总闸「切换中」卡死）：超时放弃 + 400ms 后重试一次。
  // 本应用的 POST 全是「设状态」语义（幂等），重试安全。
  const once = async () => {
    const ac = new AbortController()
    const t = window.setTimeout(() => ac.abort(), timeout_ms)
    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body ?? {}),
        signal: ac.signal,
      })
      const j = await r.json().catch(() => ({}))
      if (!r.ok || j.error) throw new Error(j.error ?? `${r.status}`)
      return j
    } finally {
      clearTimeout(t)
    }
  }
  try {
    return await once()
  } catch {
    await new Promise(res => setTimeout(res, 400))
    return once()
  }
}

// GET 同款守门：后端 400 会带 {error}，不抛的话错误对象会灌进 state 炸渲染
// （体验区面板「展不开」的根因，2026-09-20）
export async function get(url: string) {
  const r = await fetch(url)
  const j = await r.json().catch(() => ({}))
  if (!r.ok || j.error) throw new Error(j.error ?? `${r.status}`)
  return j
}
