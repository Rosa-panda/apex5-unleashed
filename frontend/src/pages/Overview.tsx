import { Zap, Gauge, Waves, ScrollText, Power } from 'lucide-react'
import type { EngineEvent, EngineSnapshot } from '../api'

const KIND_LABEL: Record<string, string> = {
  device: '设备', command: '命令', state: '状态', proxy: '代理权',
  panic: '复位', error: '错误',
}
const RESULT_COLOR: Record<string, string> = {
  ack: 'text-ok', nack: 'text-err', timeout: 'text-warn', sent: 'text-text-low',
}

export default function Overview({ snap, events, onPanic }: {
  snap: EngineSnapshot | null
  events: EngineEvent[]
  onPanic: () => void
}) {
  const trig = snap?.state.triggers
  const rumble = snap?.state.rumble

  return (
    <div className="space-y-5">
      {/* 状态卡 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="card p-5">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
            <Gauge size={14} className="text-accent" /> 扳机效果（锁存账本）
          </div>
          {(['left', 'right'] as const).map((s) => {
            const t = trig?.[s]
            return (
              <div key={s} className="mb-2 flex items-center justify-between text-[13px]">
                <span className="text-text-mid">{s === 'left' ? 'LT' : 'RT'}</span>
                {t ? (
                  <span className="tag border-accent/40 text-accent">{t.mode}</span>
                ) : (
                  <span className="tag">normal · 默认</span>
                )}
              </div>
            )
          })}
        </div>

        <div className="card p-5">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
            <Waves size={14} className="text-accent" /> 震动
          </div>
          <div className="flex items-end gap-6">
            {(['l', 'r'] as const).map((k) => (
              <div key={k}>
                <div className="mb-1 text-[11px] text-text-low">{k === 'l' ? '左马达' : '右马达'}</div>
                <div className="h-24 w-8 overflow-hidden rounded-md bg-[#0d0d14]">
                  <div
                    className="mt-auto h-[var(--v)] w-full rounded-md bg-gradient-to-t from-accent-dim to-accent transition-all"
                    style={{ height: `${((rumble?.[k] ?? 0) / 255) * 100}%`, marginTop: 'auto' }}
                  />
                </div>
                <div className="mt-1 text-center text-[12px] tabular-nums text-text-mid">{rumble?.[k] ?? 0}</div>
              </div>
            ))}
            {rumble?.updated_at && <div className="pb-6 text-[11px] text-text-low">更新于 {rumble.updated_at}</div>}
          </div>
        </div>

        <div className="card flex flex-col p-5">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
            <Power size={14} className="text-accent" /> 快速操作
          </div>
          <div className="space-y-2 text-[13px]">
            <QuickRow label="双扳机 Normal 复位" hint="清除所有锁存效果" onClick={onPanic} />
            <div className="text-[11px] leading-relaxed text-text-low">
              提示：所有效果均为锁存式——软件退出前会自动复位；异常强杀后，下次连接会做启动卫生检查自动清理。
            </div>
          </div>
        </div>
      </div>

      {/* 事件日志 */}
      <div className="card p-5">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
          <ScrollText size={14} className="text-accent" /> 事件日志
          <span className="text-text-low">· 命令收发 / 代理权变化 / 设备事件</span>
        </div>
        <div className="max-h-80 space-y-0.5 overflow-y-auto font-mono text-[12px]">
          {[...events].reverse().slice(0, 120).map((e, i) => (
            <div key={i} className="flex gap-3 rounded px-2 py-0.5 hover:bg-white/3">
              <span className="text-text-low">{e.ts}</span>
              <span className={e.kind === 'proxy' ? 'text-warn' : e.kind === 'error' ? 'text-err' : 'text-text-mid'}>
                {KIND_LABEL[e.kind] ?? e.kind}
              </span>
              <span className={RESULT_COLOR[e.result as string] ?? 'text-text-hi'}>
                {e.result ? `${e.result}` : ''}
              </span>
              <span className="truncate text-text-low">
                {typeof e.source === 'string' ? e.source : ''}
                {typeof e.hex === 'string' && e.hex ? ` [${e.hex}…]` : ''}
                {typeof e.detail === 'string' ? ` ${e.detail}` : ''}
                {typeof e.cmd === 'number' ? ` cmd=${e.cmd}` : ''}
              </span>
            </div>
          ))}
          {events.length === 0 && (
            <div className="flex items-center gap-2 px-2 py-4 text-text-low">
              <Zap size={12} /> 暂无事件——去扳机实验室试试？
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function QuickRow({ label, hint, onClick }: { label: string; hint: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="btn w-full justify-between">
      <span>{label}</span>
      <span className="text-[11px] text-text-low">{hint}</span>
    </button>
  )
}
