// API 桶文件（ADR-029 F1）：原 api.ts 的扁平 api 对象按域拆分后在此合并，
// `import { api, type Xxx } from './api'` 的调用点零改动（目录 index 解析）。
import { system } from './system'
import { control } from './control'
import { presets } from './presets'
import { games } from './games'
import { settings } from './settings'
import { macros } from './macros'
import { screen } from './screen'
import { lights } from './lights'
import { exp } from './exp'
import { motion } from './motion'

export const api = {
  ...system,
  ...control,
  ...presets,
  ...games,
  ...settings,
  ...macros,
  ...screen,
  ...lights,
  ...exp,
  ...motion,
}

export type {
  TriggerState, GripBindState, EngineSnapshot, EngineEvent, VibFixStatus, Preset,
  ExpFeature, ExpSummary, ExpList, MacroAction, Macro, LedBean, LedDetect,
} from './types'
