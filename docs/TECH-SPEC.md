# TECH-SPEC · 技术规格书（v0.1）

> 配套《APEX5-UNLEASHED-企划书.md》。已吸收两轮外部审阅修正。

## 1. 拓扑（单进程多线程）

```
Apex5Unleashed (单 Python 进程)
  主线程:   pywebview 窗口（Windows GUI 必须主线程）
  线程S:    uvicorn daemon 线程 (127.0.0.1:18765, REST+WS+静态托管前端产物)
  线程H:    HID worker（唯一读写手柄的线程）
  线程T:    pystray 托盘（自带消息循环）
  线程D:    设备监视定时器（2s 热插拔轮询 + 代理进程扫描）
```
- 启动顺序：uvicorn 先起 → 端口 ready → 再 create 窗口（防白屏）
- 单实例：端口占用即判定已有实例，退出
- 退出：托盘退出/关窗(默认缩托盘) → panic → 关设备 → 关服务；SIGINT 兜底；强杀场景由"启动卫生检查"兜底（ADR-010）

## 2. 线程H主循环（审阅修正版）

```
loop:
  1) 取写队列（互斥锁）→ 有则 hid_write（流式命令零等待直写，但共用写锁）
  2) 无则 hid_read(timeout=10ms)  ← 读永不长期阻塞，写不会被饿死
  3) 收到帧 → ACK匹配器：匹配本方 pending → 完成；不匹配 → 外部命令事件(§5)
```

## 3. 协议引擎（详见 PROTOCOL.md）

- 帧：32B `03 5A A5 <cmd> <len> <payload…>`；ACK 剥 report id 后 [2]=cmd [3]=01
- 命令队列：超时 300ms 重试 2 次；cmd 18 流式例外（不等 ACK）
- 锁存账本 state：triggers{L,R}{mode,params,source,applied_at} / rumble{l,r} / gripBind —— 先记账再发送，UI 看账本不看猜
- preview：cmd 81 apply=0 临时效果不落账本；apply=1 才落（官方 SDK onlyPreview 位）
- 参数钳位照抄官方反编译（resistance/strength<1→1 等）

## 4. 效果/预设

- 六模式封装 race/sniper/recoil/lock/vibration/normal + grip bind/unbind + rumble(自动归零)
- 预设 JSON：%APPDATA%\Apex5Unleashed\presets\（数据目录唯一化，ADR 纪律）；内置预设随包
- 应用预设 = 事务：清扳机 → 逐条下发 → 失败回滚 Normal
- 游戏适配三档（ADR-017/022/024）：官方适配（vib 手工调参，34 条）·
  DS转官（ASB 原生 DualSense 清单 181 条，参数由官方调参做题材集 k-NN 自动生成，
  tools/update_asb_vib.py 幂等重跑，Steam genres 缓存 %APPDATA%\genre_cache.json）·
  通用震动联动（任意游戏兜底，cmd 0x52 固件路由）。三档同一条 autoswitch 链路。

## 5. 代理权检测

1) 总线层：不匹配本方 pending 的回显/ACK = 外部写入铁证（记 {cmd,ts}，60s 冷却防闪）
2) 进程归因：SpaceStationService.exe(飞智)/steam.exe/DSX.exe/reWASD*/JoyToKey* → 人话显示
- 状态机：本软件代理中 ↔ 检测到其他代理:XX；只状态签+事件日志，不弹窗

## 6. 服务接口

REST: /api/health /api/device /api/state /api/trigger(POST,preview位) /api/trigger/clear
      /api/rumble /api/presets[/apply] /api/panic /api/events /api/test/pulse /api/test/sine
WS: /ws 推账本/代理权/设备事件（10Hz 合并）。仅绑 127.0.0.1，免鉴权（README 注明勿暴露端口）

## 7. Mock 设备层（ADR-011）

Transport 抽象：HidPad（真机）/ MockPad（延迟 5ms 生成合法 ACK，无手柄时自动启用）。
保证 UI 全链路离线可开发可测试；后续 CI trace 回放也挂在这层。

## 8. UI（React18+Vite+TS+Tailwind4，深色科技风）

- token：bg #0a0a0f / 卡片 #12121a / 边框 #1f1f2e / 强调 #22d3ee / 危险 #ef4444
- 四页：总览(设备卡/扳机账本卡/代理权签/panic钮/事件流) · 扳机实验室(六模式卡片+参数滑块+preview+测试台) · 鐘设库(来源徽标/应用/导入导出/另存) · 设置(关窗行为/语言占位)
- 左侧图标导航（lucide-react），无路由库（状态导航），实时走 WS hook

## 9. 错误处理/日志

- rotating 文件 %APPDATA%\Apex5Unleashed\logs\ + /api/events 双通道
- 每条下行命令四元组：时间/来源(ui|preset|panic|test)/hex/结果(ack|timeout|external)
- HID 异常 → 设备状态机回未连接重连（指数退避 2s→30s）；服务异常 500+日志

## 10. 交付

开发态：uvicorn --reload + vite dev(proxy 18765)。产品态：vite build 产物由 FastAPI 托管，PyInstaller onedir（v0.1 绿色目录，安装器 v0.3）。
