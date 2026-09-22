// 体验区功能面板（ADR-027）：交互 UI。体感四件套（陀螺/固件映射/迷宫/DSU 桥）
// 的组件仍在导出（ADR-028 迁入「体感」栏目复用），但不再注册进体验区 PANELS。
// 每个面板自治：自己拉数据、自己报错。真机类操作 mock 下会得到 400，按钮不禁用
// （用户能看见错误文案，比灰按钮更能说明「为什么不能点」）。
// ADR-029 F2：面板实现已逐字拆至 ./panels/*.tsx，本文件只做 barrel（注册表键序逐字不变）。
import type React from 'react'
import { ArbitrationPanel } from './panels/arbitration'
import { DevCfgPanel } from './panels/devcfg'
import { DiagnosticsPanel } from './panels/diagnostics'
import { FactoryResetPanel } from './panels/factoryreset'
import { GameSimPanel } from './panels/gamesim'
import { GripVibPanel } from './panels/gripvib'
import { RgbBridgePanel } from './panels/rgbbridge'
import { ScreenPlusPanel } from './panels/screenplus'
import { ShareCodePanel } from './panels/sharecode'
import { SlotsPanel } from './panels/slots'
import { StickCfgPanel } from './panels/stickcfg'
import { StickMapPanel } from './panels/stickmap'
import { SwitchBankPanel } from './panels/switchbank'
import { TurboPanel } from './panels/turbo'
import { Safe } from './ui'

export const PANELS: Record<string, React.FC> = {
  turbo: Safe(TurboPanel),
  stickcfg: Safe(StickCfgPanel),
  devcfg: Safe(DevCfgPanel),
  arbitration: Safe(ArbitrationPanel),
  stickmap: Safe(StickMapPanel),
  rgbbridge: Safe(RgbBridgePanel),
  diagnostics: Safe(DiagnosticsPanel),
  slots: Safe(SlotsPanel),
  sharecode: Safe(ShareCodePanel),
  switchbank: Safe(SwitchBankPanel),
  gripvib: Safe(GripVibPanel),
  screenplus: Safe(ScreenPlusPanel),
  factoryreset: Safe(FactoryResetPanel),
  gamesim: Safe(GameSimPanel),
}

// 体感四件套（Motion.tsx 具名导入）：实现见 panels/{gyro,gyrofw,maze,dsu}.tsx
export { GyroPanel } from './panels/gyro'
export { GyroFwPanel } from './panels/gyrofw'
export { MazePanel } from './panels/maze'
export { DsuPanel } from './panels/dsu'
