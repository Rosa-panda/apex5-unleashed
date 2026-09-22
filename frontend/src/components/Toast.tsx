// 全局 toast 的纯展示件（ADR-029 F4 自 App.tsx 原样搬出）。
// 弹出/消失的 state 与定时器逻辑留在 App.tsx——4s 定时放 ref 不能当 effect
// cleanup 的约束见 App.tsx 内注释（行为面，不随展示件走）。
import { Zap } from 'lucide-react'

export function Toast({ msg }: { msg: string }) {
  return (
    <div className="pointer-events-none absolute left-1/2 top-12 z-50 -translate-x-1/2">
      <div className="flex items-center gap-2 rounded-lg border border-accent/50 bg-[#0d0d14] px-4 py-2 text-[13px] text-accent shadow-lg">
        <Zap size={13} /> {msg}
      </div>
    </div>
  )
}
