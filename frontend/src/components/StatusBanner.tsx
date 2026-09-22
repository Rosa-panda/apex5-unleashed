// 全局离线横幅（ADR-029 F4 自 App.tsx 原样搬出）：
// 后台断了（红）/ 手柄没连（黄），让断连在任何页面都一眼可见。
import { Gamepad } from 'lucide-react'

export function StatusBanner({ connected, online, mock }: { connected: boolean; online: boolean; mock: boolean }) {
  return (
    <>
      {!connected ? (
        <div className="flex items-center gap-2 border-b border-err/30 bg-err/10 px-6 py-1.5 text-[12px] text-err">
          <Gamepad size={13} /> 无法连接软件后台（127.0.0.1:18765），正在自动重连…
        </div>
      ) : !online && !mock ? (
        <div className="flex items-center gap-2 border-b border-warn/30 bg-warn/10 px-6 py-1.5 text-[12px] text-warn">
          <Gamepad size={13} /> 手柄未连接 —— 请检查 USB 线或重新插拔手柄；接上后设备功能自动恢复
        </div>
      ) : null}
    </>
  )
}
