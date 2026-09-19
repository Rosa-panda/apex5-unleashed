// 设备离线的统一提示（ADR-021 期间补的通用体验）：
// - DeviceGate：页面级闸门，直连手柄的功能页在离线时渲染友好提示卡，不再黑屏/报错刷屏
// - 用法：<DeviceGate online={online} hint="...">{页面内容}</DeviceGate>
import type { ReactNode } from 'react'
import { Gamepad } from 'lucide-react'

export function DeviceGate({ online, hint, children }:
{ online: boolean; hint?: string; children?: ReactNode }) {
  if (online) return <>{children}</>
  return (
    <div className="max-w-4xl space-y-4">
      <div className="card flex flex-col items-center gap-2 p-12 text-center">
        <Gamepad size={30} className="text-text-low" />
        <div className="text-[15px] font-medium">手柄未连接</div>
        <div className="max-w-md text-[12px] leading-relaxed text-text-low">
          {hint ?? '这个功能直接操作手柄，没连上手柄用不了。请检查 USB 线是否插好，或重新插拔一次手柄；连上后本页会自动恢复。'}
        </div>
      </div>
    </div>
  )
}
