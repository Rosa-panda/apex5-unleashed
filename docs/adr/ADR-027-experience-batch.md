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
