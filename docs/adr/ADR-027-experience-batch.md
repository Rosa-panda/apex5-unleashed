# ADR-027 体验区全量实现（15 项软件一次做完，真机验证后置）

日期：2026-09-20 ｜ 状态：已实施 ｜ 上游：ADR-026（体验区）、《APEX5-功能挖掘-企划书.md》§二/§三

## 背景

用户指令：不要「边做边测」，把体验区全部功能一口气做成软件成品，需要用户配合的点留钩子，
最后统一真机验收。openflydigi 四文件（blobs/mapping/settings/motion）+ factory_config +
identity 研读完毕，数据层字节级答案齐全，具备直接出品的条件。

## 决策

### D1 模块切分
- `profile.py`：一切 blob 编辑的唯一入口（turbo/摇杆曲线/扳机曲线/motion 块/握把震动/标题/
  槽位/Switch 银行/恢复出厂）。自带会话锁；读写走 extkeys.Pad（第二句柄，与引擎并存）。
- `devcfg.py`：cmd3 设置块读/写（cmd19/20/21/22/23）、昵称（cmd2/24）、重启（cmd29）、
  占用方（cmd16 读）、仲裁申请（cmd28）。走引擎队列（第一句柄）。
- `softmap.py`：体感瞄准 + 摇杆→鼠键（软件层，SendInput），消费引擎 0xEF 运动分发。
- `rgbbridge.py`：DSX UDP 7878 → 灯效翻译（仅 127.0.0.1、限频 ≥1s）。
- `sharecode.py`：自有格式 `APX5-` + zlib + base62 + crc16。
- `diag.py`：摇杆散点采样 + ADC 校准（cmd240）+ 自动校准开关（cmd19 sub6）。

### D2 字节级蓝本（openflydigi 证据，全部已读原文）
- 键表 [13+i*3, 3B] = [target, turbo_mode, freq]；turbo 需真实 target。
- 摇杆：核心块 109（7B/侧：type,center,edge,p1x,p1y,p2x,p2y——源形式）+ bank 790
  （12B/侧：type,bank[9],isRound,end——**固件只播 bank**）。`stick_bank` 编译器截断不四舍五入，
  厂线 50 62 75 87 100 112 125 137 150；bank 值 = 输出百分比+50。center/edge 双极性
  （负值拒写，官方读写器编码不一致）；center=127 =「不作摇杆」哨兵；核心块 end 不可设。
- 扳机曲线 123（7B/侧：type,zero,p1x,p1y,p2x,p2y,end，满量 255）：只做 zero/end + 镜像控制点。
- motion 137（8B）：[target(0/1/2/3), enable_key, enable_type(0点按/1按住), dead_zone,
  sens_x, sens_y, use_mode(由 target 派生：1→Racer, 2→FPS, 3→FPS), enable_key2(Press 才写)]。
- 握把震动 145（9B）：[总开关(反逻辑 0=开/0xFF=关), l_on,l_min,l_max,l_scale, r_...]，min≤max。
- Switch：write blob 至 cfg_id=槽+4，然后 171 特殊帧（len=4, ver LE16@5, cfg_id@7,
  crc@8 只盖 [3,7)——官方 bug 字面复刻）。normalise：254 目标回透传、非摇杆摇杆回摇杆。
- 恢复出厂：单槽 = factory_config.for_slot(slot,"k5") 写入+保存（lighting/宏不在此列，
  UI 必须声明）；全部 = cmd175 payload [0]（槽字节无效，四槽连名字全重置）。
- data_version：每次保存随机换新（≠当前、≠0xFFFF）。
- 昵称：cmd2 回复 payload 在 body[5]（SDK 索引错位已勘误）；cmd24 写无校验和、
  固件存 len-1 字节 → payload = 名字 + 1B 垫，上限 26 字节（UTF-8）。
- cmd28 仲裁申请：build_crc(28, bytes([23,1]) + 20B tag)。
- 版本：cmd1 心跳 body[15..29) 七模块 2B BCD（main/dongle/switch/trigger/screen/adc/nearlink）。
- 0xEF 帧（body 索引，= openflydigi raw-1）：摇杆 3/5/7/9、陀螺 17/19/21、加速 23/25/27
  （i16 LE）、键位图 11..14（既有）。

### D3 软件层体感/摇杆映射
官方像素常数未知部分（位移增益）暴露为可调参数 + UI 注明「手感待真机调」；算法骨架
（GyroScale=1000/16384、死区 |raw|<8、曲线阈值 2 指数 1.3、灵敏度/50）按反编译照抄。

### D4 危险项
- 恢复出厂（单槽/全部）双确认（输入 FIVE 字符）+ 先全量备份（四槽 blob + 灯表 →
  %APPDATA%\Apex5Unleashed\backup_<ts>\）。
- RGB 桥只监听 127.0.0.1。

### D5 体验区纪律不变
默认全关（enabled 翻开在实现完成后）、判定三态、注册表驱动 UI。mock 模式下真机类端点
统一返回明确错误（`需要真机`），前端禁用按钮。

## 实现记录（2026-09-20 当日完成）

**后端**：`profile.py`（blob 编辑全家桶 + ProfileService 会话锁/读后复原活跃槽/出厂 blob/
171 bug 复刻）、`devcfg.py`（settings/昵称/重启/owner 解析/acquire payload）、`softmap.py`
（GyroAim + StickMap + SoftMapHub + SendInput）、`rgbbridge.py`、`sharecode.py`、`diag.py`。
**engine.py**：0xEF 运动解码+subscribe_motion（body 索引 = openflydigi raw−1：摇杆 3/5/7/9、
陀螺 17/19/21、加速 23/25/27；运动高频不走事件日志防刷屏）；cmd1 心跳抓七模块版本
（P4 探针就地作废）；request()/send_checked() 阻塞问答；attach 后 1s 读 cmd16。
**service.py**：/api/exp/{profile,turbo,stick,trigger-curve,motion,gripvib,title,slots,
slots/apply,profile/switch,factoryreset/slot,factoryreset/all,devcfg,devcfg/setting,
devcfg/nickname,devcfg/reboot,owner,owner/acquire,gyro,stickmap,rgbbridge,diagnostics,
sharecode/*}；危险项 confirm 字符串门 + 全量备份先行（四槽 blob+灯表→backup_时间戳\）。
**explab.py**：15 项 enabled=true。**前端**：pages/exp/panels.tsx 15 面板（键表连发表/
曲线双层画布[源形式折线+bank 九点]/设置表单/体感遥测/散点体检/分享码/四槽/危险区
RESET·RESET-ALL 解锁）+ ExpLab 卡片展开 + api.ts 23 个端点。

**冒烟（真机在线，全只读，写路径未动）**：
- /api/exp：15 项全 enabled ✓
- /api/exp/profile：槽0、23 键、dv=29650、bank 解码 0..100（出厂恒等线）✓
- /api/exp/devcfg：sleep=15、rate_raw=0（k5 已知）、precision=2（10bit）、sens=17、昵称空 ✓
- 版本（cmd1 自动解码）：主控 7.0.4.5 / Switch 4.5.2.9 / 屏幕 0.1.2.8 / 星闪 1.1.3.1 ✓
- /api/exp/owner：control_by 空标签、xinput=1、third_party=0 ✓
- 分享码：真机档案编码 262 字符 → 解码回环一致 → 坏码 400 ✓
- gyro/stickmap/rgbbridge/diagnostics 状态端点 ✓；npm build ✓

**留给用户真机验收的钩子清单**：
1. 体感瞄准 `gain`（像素增益）与 yaw/pitch 轴向默认值（z/x）——手感与轴向要真机调；
2. cmd28 acquire 的固件语义（发了、ACK 了，但设备行为待对照空间站观察）；
3. cmd240 ADC 校准报文细节（RESEARCH 推断，UI 已标注）；
4. 回报率 k5 读回 0=默认，写具体档（1/2/4/8）待验；
5. P1/P2/P3/P5 探针（退出工具后跑）结论回填企划书；
6. Switch 银行同步（写槽 4..7 + 171）需 Switch 主机或 Switch 模式手柄验证。

## 追加（2026-09-21）：#16 模拟游戏场（gamesim）

用户驱动：不下真游戏也要能联调全功能。定位「工具自己给自己当一个游戏支持」，
进体验区注册表（tier 2）。四个测试场：
- **扳机场**：gamesim 场景线程（射击 6s/爆炸/赛车 8s/松开复位）发 DSX 协议 JSON
  到 ingress 实际端口——与官方 Mod 完全同链路。真机冒烟：54 发 54 收 51 applied。
- **灯场**：低血量红/回血绿/熄灯 → RGB ASCII 发灯效桥实际端口。
- **靶场**（前端本地）：鼠标轨迹淡出 + 随机靶打分——体感瞄准/摇杆→鼠标闭环验证。
- **键盘场**（前端本地）：keydown 真实按下计数（ev.repeat 滤掉系统重复）+ 2s 窗口
  实时频率——连发 Turbo/宏/摇杆→键盘闭环验证。
端点 GET/POST /api/exp/gamesim（scenario=stop 停止）。0xF5 直点色语义仍是验收钩子。

## 追加（2026-09-21）：#17 体感弹珠迷宫（maze）

起因：用户怀疑「手柄好像没有真体感」。实测（真机）：0xEF 运动流活水——
加速度模长 ~4094（Z 轴 1g 平放）、陀螺实时变化、帧率 ~300Hz。
**实锤：八爪鱼5 PC 模式固件持续输出六轴数据，硬件无虚。**
（副产品修复：GyroAim.on_motion 遥测常开——此前 enabled=False 提前 return
导致 frames 恒 0，误判无数据。）

实现：
- `maze.py` MazeService：订阅运动流；加速度计重力向量解算倾斜（平放校准取
  1g 基准，量程无关）；加速度模长 <50 时退化陀螺仪积分（带回中衰减）。
  has_imu/raw_accel/raw_gyro 直出——面板即自检答案器。
- 前端 MazePanel：物理在 JS（60fps），40ms 轮询 tilt；墙 AABB 圆碰撞反弹、
  3 洞 + 终点、掉洞动画、左右/前后反转存 localStorage。
- 加速度标定实测：~4094/1g（非 openflydigi 的 16384 陀螺量纲，别混用）。
端点 GET/POST /api/exp/maze（op=calibrate）。

## 追加（2026-09-21）：#17 v2 姿态融合 + 出厂标定逆向结论

用户质疑：「飞智做了出厂标定，为什么我们不能逆向拿数据？迷宫纯加速度计是死路。」

**逆向结论：出厂标定公开渠道拿不到，且没必要。** 三层证据：
1. openflydigi 全仓库（本地通读 motion.py/PROTOCOL.md/device-settings.md）：无任何 IMU
   标定读取命令；accel 4096/g 是作者硬编码实测，陀螺量纲原文写明「无参照、靠手感调」。
2. Linux 内核 6.17（Phoronix 确认）：Apex5 支持走 xpad（摇杆/按键），驱动完全不碰 IMU。
3. DS5 模拟路径：openflydigi 的 DualSense 模式是 usbip 用户态虚拟设备，feature 0x05
   标定 blob 抄自真索尼手柄（ds5-dump-features 工具原文），不经过飞智固件 NVM。

出厂标定本质 = 每轴零偏+增益一组常量；主机用它是没法跑在线估计。我们在线估计
（静止低通收敛）随温漂更新，比 NVM 常量更准——这正是 Switch/PS5「开机平放校准」
的原理，不是妥协。

**maze.py v2：互补滤波姿态解算**（替代 v1 加速度计裸倾角——静止完美、一动就被
线加速度污染，即「死路」）：
- 陀螺零偏自动跟踪（静止期低通 BIAS_ALPHA=0.05，全部模式统一去零偏）
- 融合主路径 `source="fusion"`：tilt = accel 倾角·w + (tilt+陀螺积分)·(1-w)，
  w=0.03/帧（~300Hz → 时间常数 ~0.11s）；静止期 w=1 直接收敛重力向量
- 陀螺量纲假设 GYRO_DPS_PER_LSB=0.05（openflydigi 同款，未实测，可调钩子）
- dt 钳制 0.05s 防断流跳帧；v1 陀螺退化模式保留（加速度缺失时，带回中衰减）
- status 新增 gyro_bias 字段；前端 source 判断只区分 gyro_fallback，无需改
- 真机冒烟：source=fusion、rest=(-3.29,1.23,4093.6) 自动收敛、
  gyro_bias=(0.80,0.13,0.98)、静止 tilt≈0 ✓

### v3（同日）：绝对重力锚点——修「竖放一会儿就变成新平地」

用户真机实测：竖着手柄放一会儿，迷宫把它当平地。根因 = v2 的重力基线在**任何**
静止姿态下低通刷新，「当前静止姿态」会偷换成锚点。
- 重力锚点只在**平放姿态**（|az|/mag > 0.7，FLAT_Z_RATIO）且静止时收敛；
  竖放/侧放静止只更新陀螺零偏（零偏与姿态无关，锚点与姿态有关）。
- 倾角改**绝对重力角**：tilt = -(ax-rest_x)/mag（sin 值，平放 0、竖直 ±1），
  不再是「相对当前姿态的偏差」；rest 只扣安装面小偏差（<0.1g）。
- status 新增 anchor 字段（flat 收敛中/held 非平放保持/moving），面板一行小字直显。
- 「立即校准」按钮保留为显式锚点覆盖（用户主动要求以当前姿态为平时才点）。
- 冒烟：anchor=flat、tilt≈0、rest=(-2.60,6.20,4095.3) ✓

### v4（同日）：锚点采一次即冻结——校准是动作不是过程

用户第二轮实测：v3 仍在持续收敛锚点——「锚点我已经锚定了，还自己校准？」。
定位纠偏：自动校准只该发生在**用户不知情时的首次锚定**（开机时手柄就在桌上
这种场景），锚定之后软件不得再替用户改「哪里是平」。
- 重力锚点：平放静止连续 ~40 帧（0.15s）**一次性采集**，之后冻结；
  只有「重设锚点」按钮（原立即校准）显式重设。
- 持续后台跟踪的只剩陀螺零偏（与姿态无关、不影响「哪里是平」、用户无感，
  只让融合不漂）——向用户明示这一层不是校准。
- status 新增 anchor_locked；autocal 语义改为「锚点已锁定」；前端文案
  去掉「自动校准中」改为「平放静止中正在锚定/已锁定（软件不会再动它）」。
- 冒烟：anchor_locked=true、锚点单帧采定、tilt≈0 ✓
