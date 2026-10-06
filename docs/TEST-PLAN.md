# TEST-PLAN · 测试计划

## v0.1 验收（✅ 全部通过 = v0.1 完成）

> 状态戳：v0.1 已通过。下表逐条标注，作为回归基线保留。

| # | 条目 | 方法 | 通过标准 | 状态 |
|---|---|---|---|---|
| 1 | Mock 全链路 | 无手柄启动 | UI 四页可用无报错，账本/预设/测试台在 Mock ACK 下工作 | ✅ v0.1 已通过 |
| 2 | 真机连接 | 手柄 2.4G/USB 上线 | /api/device 显示在线；启动卫生 panic 已执行(事件日志可见) | ✅ v0.1 已通过（**需真机**） |
| 3 | 实验室 preview | 拖滑块 | 50ms 防抖内效果变化；不落账本；"应用"后落账本 | ✅ v0.1 已通过（**需真机**） |
| 4 | 账本一致性 | 应用 Race 后重启软件 | 账本重读 = 手柄实际（重连后状态签恢复） | ✅ v0.1 已通过（**需真机**） |
| 5 | 代理权-进程 | 开飞智空间站 | ≤5s 状态签切"检测到其他代理:飞智" | ✅ v0.1 已通过（**需真机**） |
| 6 | 代理权-总线 | 用 probe 工具发 cmd18 | 事件日志出现 external 命令记录，状态签切换(60s冷却) | ✅ v0.1 已通过（**需真机**） |
| 7 | 预设闭环 | 保存→应用→导出→删→导入→再应用 | 效果一致 | ✅ v0.1 已通过 |
| 8 | 退出卫生 | 托盘退/关窗缩托盘退 | 手柄无残留效果（扳机Normal、马达0） | ✅ v0.1 已通过（**需真机**） |
| 9 | 单实例 | 双启动 | 第二实例退出并提示 | ✅ v0.1 已通过 |
| 10 | 托盘三态 | 断手柄/外部代理/正常 | 灰/琥珀/绿图标正确 | ✅ v0.1 已通过（**需真机**） |

## v0.2 验收（官方 Mod 管家 + DSX ingress + 游戏震动修复 + 五档适配）

> 依据：ADR-025（Mod / ingress）、README「游戏震动修复」、ADR-017/022/024（五档适配）。
> 每条标注 **需真机 / 纯 Mock**；标注「需真机」的条目在 `docs/DEV-STATUS.md` §7 真机验收表有对应行。

| # | 条目 | 方法 | 通过标准 | 需真机 | 状态 |
|---|---|---|---|---|---|
| V2-1 | 官方 Mod 下载 | 游戏库 Mod 卡点下载 | CDN 下载成功，进度可见，失败有错误提示 | 否（联网即可） | ⬜ 待测 |
| V2-2 | 官方 Mod 安装 / 启用 | 安装 → 启用 → 卸载 | 安装落盘路径正确；启用状态持久化；卸载清理干净 | 否 | ⬜ 待测 |
| V2-3 | Mod 前台驱动拉起 / 退出收尾 | 切到已装 Mod 的游戏 → 切走 | 进前台自动拉起 Mod；退出自动收尾（无残留进程） | **需真机** | ⬜ 待测 |
| V2-4 | DSX ingress 收包（飞智包） | Mod 运行时看事件日志 | 飞智包直通 cmd51，`/api/state` 可见 event 命中 | **需真机** | ⬜ 待测（ADR-025 明载待实测） |
| V2-5 | DSX ingress 收包（DSX 社区包） | DSX 社区包 / 自造 UDP 包打 7878 | 翻译层产出近似效果；被丢弃的 RGBUpdate/PlayerLED 等也翻译出来 | 否（UDP 可本机自造） | ⬜ 待测 |
| V2-6 | ingress 端口退让 | 7878 被占用时启动 | 自动退到 8787 且日志可见；占用方识别 ⬜（PRD P2-5，未实现） | 否 | ⬜ 待测 |
| V2-7 | 游戏震动修复（临时） | 设置页一键临时修复 | 经 UAC 授权后 XInput 0 号槽释放；**退出后自动还原**；账本 `vibfix.json` 留痕 | **需真机** | ⬜ 待测 |
| V2-8 | 游戏震动修复（永久） | 设置页显式点永久禁用 | 重启仍生效；必须区别于临时项（不可默认） | **需真机** | ⬜ 待测 |
| V2-9 | 游戏库五档适配命中 | 前台切到五类游戏 | 官方适配 / DS转官 / DS转官·通用 / 题材适配 / Mod 条目各自正确命中并提示 | 否（注入假 foreground_exe 即可） | ⬜ 待测 |

## v0.3 验收（体感四件套 + 灯光工坊 + 拓展键/宏完善 + 打包发布）

> 依据：ADR-027/028（体感）、ADR-018/033/034（灯光）、ADR-030/031/032（拓展键/宏）、`backend/apex5.spec`（打包）。

| # | 条目 | 方法 | 通过标准 | 需真机 | 状态 |
|---|---|---|---|---|---|
| V3-1 | 陀螺瞄准（软件层映射） | 体感中心开启后晃手柄 | 鼠标按设定灵敏度跟随；关闭后立即停止 | **需真机** | ⬜ 待测 |
| V3-2 | 固件陀螺映射 | 陀螺映射面板设定目标（摇杆 / 按键）后写固件 | 真机倾斜按设定映射输出；读回配置与面板显示一致（ADR-027） | **需真机** | ⬜ 待测 |
| V3-3 | DSU 桥 97Hz | Yuzu / Cemu 接入 `127.0.0.1:26760` | 模拟器识别为 DS 手柄；体感数据速率 ≈97Hz（ADR-028 真机实测值，允许 90~100Hz） | **需真机**（Yuzu 侧可本机跑） | ⬜ 待测 |
| V3-4 | 迷宫试玩场 | <｜hy_place▁holder▁no▁813｜>物理倾斜 | 迷宫球滚动方向与实际倾斜一致；布局从起点到终点连通（`tools/_maze_check.py`） | **需真机**（布局可纯 Mock） | ⬜ 待测 |
| V3-5 | 灯光进页还原 | 任设一灯效 → 关软件 → 重开进灯光页 | 当前灯效（含非库内的「外来灯效」逐帧回放）被正确认出并回显 | **需真机** | ⬜ 待测 |
| V3-6 | 外来灯效逐帧回放 | 用 `/api/led/apply_frames` 写非标准帧表 → 进页 | 识别为外部灯效并可逐帧回放，不崩溃、不错认成库内灯效 | **需真机** | ⬜ 待测 |
| V3-7 | 一键关灯 | 灯光页点关灯 | 所有灯熄灭且写 `led_save_flash`（否则休眠后恢复） | **需真机** | ⬜ 待测 |
| V3-8 | 灯表备份 / 还原 | 备份 → 改灯效 → 还原 | 还原后与备份字节级一致 | **需真机** | ⬜ 待测 |
| V3-9 | 键表单一所有权（ADR-032） | 宏占用 M3 → 映射卡改 M3 | 改不掉，返回 `skipped` 且 UI 标「宏占用」；删宏后自动回落 | 否（Mock 链路） | ⬜ 待测 |
| V3-10 | 拓展键一等键语义（ADR-031） | 按 M1–M6 | 手柄图上对应的 M 键亮（不是 LB/RB 等别名）；默认透传不写设备 | **需真机** | ⬜ 待测 |
| V3-11 | Windows 打包发布 | CI 打包 / 本地 PyInstaller | `Apex5Unleashed-v*-win64.zip` **解压即用**（无需 Python / Node）；首启打出 `%APPDATA%\Apex5Unleashed\apex5.log` | 否 | ⬜ 待测 |


## ApexSenseBridge 裸跑实测标准（**已废弃**，路线随 ADR-020 删除）

> 结论先行：B3 实测链路健康（p50=68µs），但 B4 判死——PC 上 DS 输入实际依赖 Steam Input
> 翻译层，消费端结构性缺失；叠加 USBip/HidHide 卸载引发的 USB 栈事故，路线整体放弃
> （ADR-020 revA 封存 → revB 全量删除，代码零残留）。下表仅作决策史存档。

| # | 条目 | 通过标准 |
|---|---|---|
| B1 | 安装 | USBip+HidHide 装完，虚拟 DS 出现在游戏/系统 |
| B2 | Steam 识别 | Steam 显示 DualSense；按需关闭 Steam Input |
| B3 | **延迟** | 体感对比：扳机效果与画面事件的感知延迟 <50ms（主观可接受线） |
| B4 | 效果质量 | 至少 2 款 DS 大作（如战神/对马岛）自适应扳机事件级变化可辨 |
| B5 | 冲突 | 与官方软件共存仲裁验证 |

~~B3/B4 不过 = 桥接路线降级（回预设路线为主），需 ADR 记录。~~ → 已记录（ADR-020）。

## CI 策略（落地状态：最后更新 v0.3.3，2026-10-06 CI 三连修后）

> 该四条全绿后 `release.yml` 才打包（严格门禁，TASK-BREAKDOWN Q6 建议在此次采纳）。

| # | 环节 | 命令 | 需真机 | 状态 |
|---|---|---|---|---|
| 1 | 协议引擎单测（帧构造 / ACK 解析 / 钳位 / 灯表容量） | `python -m pytest backend -q` | 否（纯 Mock） | ✅ 已落地（T03.2 + T04.1） |
| 2 | 脚本式单测批量喂入 | `python tools/run_script_tests.py` | 否（纯 Mock） | ✅ 已落地（T03.4） |
| 3 | Mock 全链路冒烟 | `python tools/run_smoke.py` | 否（自动起 Mock 服务） | ✅ 已落地（T03.3） |
| 4 | 前端构建 | `cd frontend; npm ci; npm run build` | 否 | ✅ 已落地（T03.1） |
| 5 | Transport 层 trace 回放（ADR-011 预留） | `tools/record_trace.py` + `backend/test_trace_replay.py` | **录制需真机 1 次**，回放纯 Mock | ⬜ 待办（T04.5 / PRD P2-6） |

**排除项**（不进 CI，见 `tools/run_script_tests.py` 的 `--local` 名单）：

| 脚本 | 排除原因 |
|---|---|
| `backend/smoke_test.py` | 命名命中 pytest 收集规则，模块级直连 `127.0.0.1:18765` → CI 无人起服务必 ConnectionRefused；已由 `backend/conftest.py` 的 `collect_ignore_glob` 兜底，CI 改走 `tools/run_smoke.py` |
| `backend/test_grip_real.py` | 走运行中后端 HTTP API，**需真机**（归属 T05） |
| `backend/test_screen_offline.py` | 第 2 项依赖本机 `C:\Program Files\Flydigi Space Station\...\default_screen_image_*.bin`，未装官方软件时必失败 → 标注「需本机官方软件」，仅在 `--local` 下跑 |

**⚠ 排除必须双登记（2026-10-06 CI 实锤的教训，commit `7ade79f`）**：

脚本式测试（模块级 `assert`、无 `def test_*`）**同样会被 pytest 按文件名收集**，模块级
assert 在收集（import）阶段就会执行——只登记 `run_script_tests.py` 的 `--local` 名单、
忘了加进 `backend/conftest.py` 的 `collect_ignore*`，CI 上 pytest 照样在收集阶段崩掉
（`test_screen_offline.py` 即此故）。**新增脚本式测试的登记清单：**

1. `tools/run_script_tests.py`：加进 `CI_TESTS`（纯 Mock）或 `LOCAL_ONLY_TESTS`（需本机环境）；
2. `backend/conftest.py`：若它不该被 pytest 收集（模块级副作用 / 需本机环境），必须同时加入
   `collect_ignore_glob` 与 `collect_ignore`；
3. 推送前自检：`python -m pytest backend -q --collect-only` 全绿收集才算数。

**CI 环境约定**：ci.yml / release.yml 两个 workflow 的 job 级 `env` 固定
`PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`——Windows runner 默认 stdout 是 cp1252，
脚本打印中文会 `UnicodeEncodeError`（run_script_tests.py CI 实锤，commit `a8082e2`）。
**改 workflow 时不可删这两个变量**；新增打印中文的脚本无需特殊处理，但禁止在
workflow 里单独改回编码。
