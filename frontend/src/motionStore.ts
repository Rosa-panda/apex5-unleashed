// 最新体感帧（后端 WS 30Hz 推送，ADR-028 补丁）。
// 刻意不用 React state：30Hz setState 会把整页拖进渲染风暴（旧版 40ms HTTP 轮询
// 又挤又卡的另一个根因）。物理 rAF 循环直接读本对象——零渲染、零延迟。
export const motionStore = {
  tilt: [0, 0] as [number, number],
  source: '',
  frames: 0,
  hasImu: false,
  autocal: false,
  anchor: '',
  ts: 0,               // performance.now()，供 UI 判断流是否活着
}

export function motionApply(evt: Record<string, unknown>) {
  const t = evt.tilt as number[] | undefined
  if (t && t.length >= 2) motionStore.tilt = [t[0], t[1]]
  motionStore.source = (evt.source as string) ?? ''
  motionStore.frames = (evt.frames as number) ?? 0
  motionStore.hasImu = !!evt.has_imu
  motionStore.autocal = !!evt.autocal
  motionStore.anchor = (evt.anchor as string) ?? ''
  motionStore.ts = performance.now()
}
