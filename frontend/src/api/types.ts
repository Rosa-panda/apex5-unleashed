// 类型定义（ADR-029 F1 自 api.ts 拆出，逐字搬迁）
export interface TriggerState { mode: string; params: Record<string, number>; source: string; applied_at: string }
export interface GripBindState { source?: string; applied_at?: string }
export interface EngineSnapshot {
  device: { kind: string | null; online: boolean; battery?: { level: number; charging: boolean } | null }
  state: {
    triggers: { left: TriggerState | null; right: TriggerState | null }
    rumble: { l: number; r: number; updated_at: string | null }
    gripBind: { left: GripBindState | null; right: GripBindState | null }
  }
  proxy: { holder: string; detail: string; since: string | null; mild?: boolean }
  events: EngineEvent[]
}
export interface EngineEvent { ts: string; kind: string; hist?: boolean; [k: string]: unknown }
// 游戏震动修复（飞智虚拟手柄抢 XInput 0 号槽）：absent=没装 / enabled=活跃会吞震动 / disabled=已禁用
export interface VibFixStatus {
  state: 'absent' | 'enabled' | 'disabled'
  service: string
  auto: boolean
  ledger: { mode: 'temporary' | 'permanent' | 'restore' | null; state: string | null; since: string | null;
    history: Array<{ ts: string; action: string; state: string }> }
}
export interface Preset {
  id: string; name: string; note: string; builtin: boolean
  actions: Array<Record<string, unknown>>; saved_at?: string
}
export interface ExpFeature {
  id: string; tier: 1 | 2 | 3; plan: string; title: string; desc: string
  enabled: boolean; tierLabel: string; verdict: 'good' | 'bad' | 'pending'; note: string
}
export interface ExpSummary { good: number; bad: number; pending: number }
export interface ExpList { ok: boolean; features: ExpFeature[]; summary: ExpSummary }
export interface MacroAction { t: number; key: number; ev: number }
export interface Macro {
  key_id: number; type: number; interval: number; actions: MacroAction[]
}
export interface LedBean {
  version: number; click_feedback: number; loop_start: number; loop_end: number
  loop_time: number; brightness: number; rgb_num: number; led_mode: number; grip_sync: number | null
}
// 帧表反推结果：known=false = 官方/第三方灯效，灯效库未收录（UI 只读展示）
export interface LedDetect { mode: string; colors: number[][]; known: boolean }
