// 引擎状态 hook：REST 拉首帧 + WS 增量（断线 3s 重连）
// 在线状态三重保障：WS snapshot（连接/重连时）→ WS device 事件（热插拔实时）→
// 3s /api/health 轮询兜底（事件万一丢包也能在 3s 内追平）。
import { useEffect, useRef, useState } from 'react'
import { api, type EngineEvent, type EngineSnapshot } from './api'
import { motionApply } from './motionStore'

export function useEngine() {
  const [snap, setSnap] = useState<EngineSnapshot | null>(null)
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<EngineEvent[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let closed = false
    let timer: number | undefined

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws`)
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onmessage = (m) => {
        const evt = JSON.parse(m.data)
        if (evt.kind === 'snapshot') {
          const { ts, kind, ...rest } = evt
          setSnap(rest as EngineSnapshot)
          // 历史事件打 hist 标记：toast 只认实时推送（重连/开窗重放历史不再误弹提示）
          setEvents(((rest as EngineSnapshot).events ?? []).map(e => ({ ...e, hist: true })))
        } else if (evt.kind === 'device') {
          // 热插拔实时感知：后端 attach/detach 都会发（monitor_loop 2s 轮询）
          setSnap((s) => s ? {
            ...s,
            device: { kind: (evt.dev_kind as string | null) ?? s.device.kind, online: !!evt.online },
          } : s)
          setEvents((e) => [...e.slice(-199), evt])
        } else if (evt.kind === 'motion') {
          // 体感帧（30Hz）：只进 motionStore（普通对象），绝不 setEvents/setSnap——
          // 30Hz 渲染风暴会卡死整页；物理 rAF 循环自己读 store
          motionApply(evt)
        } else if (evt.kind === 'battery') {
          // 电量心跳（~30s 一次，变化才发）：level 0..5，charging=充电中
          setSnap((s) => s ? {
            ...s,
            device: { ...s.device, battery: { level: evt.level as number, charging: !!evt.charging } },
          } : s)
          setEvents((e) => [...e.slice(-199), evt])
        } else {
          if (evt.kind === 'state') {
            setSnap((s) => s ? { ...s, state: evt.state, proxy: evt.proxy } : s)
          }
          setEvents((e) => [...e.slice(-199), evt])
        }
      }
      ws.onclose = () => {
        setConnected(false)
        if (!closed) timer = window.setTimeout(connect, 3000)
      }
      ws.onerror = () => ws.close()
    }

    api.state().then(setSnap).catch(() => {})
    connect()

    // 兜底轮询：health 只回 3 个字节段，代价可忽略；插拔事件万一丢了也能追平
    const poll = window.setInterval(() => {
      fetch('/api/health').then(r => r.json()).then((h: { mock: boolean; online: boolean }) => {
        setSnap((s) => s && s.device.online !== h.online
          ? { ...s, device: { ...s.device, online: h.online } }
          : s)
      }).catch(() => {})
    }, 3000)

    return () => {
      closed = true
      if (timer) clearTimeout(timer)
      window.clearInterval(poll)
      wsRef.current?.close()
    }
  }, [])

  return { snap, connected, events }
}
