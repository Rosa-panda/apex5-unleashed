// 体感/0xEF 流域（ADR-029 F1 自 api.ts 拆出）：陀螺瞄准/摇杆映射/灯桥/迷宫/DSU/仿真/总闸
import { get, post } from './http'

export const motion = {
  expGyro: () => get('/api/exp/gyro') as Promise<any>,
  expGyroSet: (patch: Record<string, unknown>) => post('/api/exp/gyro', { patch }) as Promise<any>,
  expStickMap: () => get('/api/exp/stickmap') as Promise<any>,
  expStickMapSet: (patch: Record<string, unknown>) => post('/api/exp/stickmap', { patch }) as Promise<any>,
  expRgb: () => get('/api/exp/rgbbridge') as Promise<any>,
  expRgbSet: (enabled: boolean, port = 7878) => post('/api/exp/rgbbridge', { enabled, port }) as Promise<any>,
  expRgbTest: (rgb: number[]) => post('/api/exp/rgbbridge/test', { rgb }) as Promise<any>,
  expRgbFlash: (enabled: boolean, rgb: number[]) => post('/api/exp/rgbbridge/flash', { enabled, rgb }) as Promise<any>,
  expSim: () => get('/api/exp/gamesim') as Promise<any>,
  expSimRun: (scenario: string) => post('/api/exp/gamesim', { scenario }) as Promise<any>,
  expMaze: () => get('/api/exp/maze') as Promise<any>,
  expMazeCal: () => post('/api/exp/maze', { op: 'calibrate' }) as Promise<any>,
  expDsu: () => get('/api/exp/dsu') as Promise<any>,
  expDsuSet: (enabled: boolean, port = 26760, invert: boolean[] | null = null) =>
    post('/api/exp/dsu', { enabled, port, invert }) as Promise<any>,
  expImu: (enabled: boolean) => post('/api/exp/imu', { enabled }) as Promise<any>,
  // 体感总闸（ADR-028）：联动 运动流+模拟器桥+陀螺瞄准，状态持久化在后端
  motionMaster: () => get('/api/motion/master') as Promise<any>,
  motionMasterSet: (enabled: boolean) => post('/api/motion/master', { enabled }) as Promise<any>,
  // 0xEF 流心跳（ADR-028 修订 2）：拓展键监听期间每 15s 打卡，30s 无人打卡自动收流
  rawStream: (on: boolean) => post('/api/rawstream', { on }) as Promise<any>,
}
