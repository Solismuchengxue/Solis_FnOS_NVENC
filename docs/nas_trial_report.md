# 飞牛临时实测与恢复报告

状态：**有限现场包已收尾；新库服务接入未通过；当前可用版本恢复 PASS**。日期：2026-10-10。本报告是本包运行/集成证据的共享权威，项目意图仍见 [Blueprint](blueprint.md)，授权范围见[方案](nas_trial_plan.md)。

## 授权、目标与时间

已只读读回来源聊天 `[D60]Solis_Pvescript负责人`（`01a089f2-db0d-7c42-88dc-9a1de7dfb1cb`）的直接用户消息 `01a121a8-043b-7640-9c9e-f10fdbb9a8e6`：“批准，没人正在看片”。授权是单个 mediasrv 的临时实测与恢复当前可用版本，不是长期启用。负责人聊天中的后续确认仅允许失败/取消后的指定密码窗口重试，没有扩大现场范围。

正式 cwd 和 Git 根均为 `F:\60_Infrastructure_and_Operations\Solis_FnOS_NVENC`。SSH 入口使用当前配置绑定的 `fnos`；不将地址、密钥路径或凭据写入共享报告。现场阶段记录为北京时间 **01:21:13–01:48:15**（UTC 2026-10-09 17:21:13–17:48:15），服务临时接入从 01:39:59 开始，01:40:21 完成恢复；最终只读复核至 01:57:02。实际主机为 x86_64 / Debian 12，GPU 为 GRID P4-4Q，驱动 535.309.01；具体 fnOS 软件版本和 License 状态未核查。

没有重建候选、修改固定核心/补丁/headers/镜像、安装包、修改驱动/Toolkit/网络/PVE/VM、写入 `/etc` 持久覆盖或重启 NAS。没有 commit、push、remote 或 GitHub 操作。

## 结果分层

| 项目 | 本轮结果 | 直接证据与限制 |
| --- | --- | --- |
| 新库依赖/身份 | PASS | 传输 SHA 与本地 run1 一致；SONAME `libavcodec.so.62`；现场依赖无 `not found` |
| H264 NVENC | PASS，有限独立编码 | 合成输入 3 秒、75 帧、1280×720；退出 0；新库真实映射、CUDA/encode 库、NVENC API12.1 初始化和输出回读 |
| HEVC NVENC | PASS，有限独立编码 | 同样 3 秒、75 帧、1280×720；退出 0；新库映射与 API12.1 初始化；两项总媒体时长 6 秒 |
| AC4 官方 demux/48k 链路 | FAIL：不完整输出 | 合法 6 秒短样本识别为 AC4/51200 Hz/双声道，但重采样只得到 1 秒 48000 Hz PCM，并出现 sequence counter / invalid packet 错误；退出 0 不构成 PASS |
| 新库 mediasrv 接入 | SETUP_FAILED | 本包将库放到 `/run`；该挂载有 `noexec`，启动日志明确为 `libavcodec.so.62: failed to map segment from shared object`，主进程退出 127 |
| 新库原生 720p/跳转/听感 | NOT_VERIFIED | 新库未进入有效服务运行，不能借用独立编码或恢复后的播放结果 |
| 当前可用基线恢复 | PASS | 仅撤回本包 95 覆盖；新 PID、库映射/SHA、有效 LD_LIBRARY_PATH 与原 90 覆盖均回到现场基线 |
| 恢复后的原生流程 | PASS，单片有限观察 | H264/8-bit、AAC 输入；video 实际 1280×720，readyState=4、播放进度增加；跳转后缓冲并继续，手动暂停/继续也成功；用户确认声音正常、无明显不同步 |
| 保护与临时收尾 | PASS，有界；最后另见容器变化 | 11 项文件 SHA/原权限、trim-media PID 与运行容器 ID 集合在恢复/清理时一致；本包临时资源已保全后清理；最后复核容器集合变化原因 UNKNOWN |

恢复后的播放观察不归入新库测试。声音确认对应恢复后的一路播放；没有独立听音、逐帧同步测量或跳转后单独声音确认。跳转观察不能证明即时、无缓冲或所有时间点均可无缝续播。

## 当前可用基线与恢复合同

现场原可用库为 `/opt/solis-fnos-nvenc/ffmpeg-8.1.1-api12.1/candidate-lib/libavcodec.so.62`，SHA256 `3d7e7e241715fb6a3468a4d47d0fdaef3e6b79cecc3d3bb1f6d3118fac265367`。原 mediasrv PID 为 437241，恢复及最终复核 PID 为 938195；PID 仅为这次观察值。

原有效覆盖 `/run/systemd/system/mediasrv.service.d/90-solis-nvenc-compat.conf`，SHA256 `89cdc6f153652484656a1b730f7e557660692bc90e8c335361328ace17a9fc60`。原单元 SHA256 `ef43c271aae4cdb45f4c2f39d7e360a26c7b7783ac483c2e7a7df2ee733bd15a`。恢复后的服务和实际进程环境均为候选历史目录加两个官方库目录，实际 libavcodec 映射/SHA 一致；官方 libavformat/libavutil/libswresample 映射也读回。

本包只新加 `95-solis-nvenc-trial-01a121a8.conf`。失败后退役这一个文件，执行 daemon-reload/restart 并读回，而没有调用针对官方基线的通用 rollback。当前服务仍使用用户原可用历史版本，**没有回到官方 libavcodec，也没有留用新 run1**。

11 项保护包括原单元、90 覆盖、历史库、官方 ffmpeg/ffprobe/四个 FFmpeg 库、mediasrv 与真实 trim-media 二进制。SHA 前后相同，恢复时原 mode/uid/gid/文件类型也相同。trim-media PID 7040 未变。运行容器 ID 集合在恢复及 01:48:15 清理门一致；01:56:13/01:57:02 的最后只读复核仍有 15 个，但 **1 个 ID 离开运行集合、1 个 ID 进入**。已确认显式本地 Docker socket 与 default context 的当前集合相同；变化原因 **UNKNOWN**，本包没有容器写命令。证据不能证明其内部业务状态、所有停止容器或从清理到最后复核期间的全局保全；不扩大调查或修复。

01:56:13 再次读回 mediasrv PID 938195、active/running、原 90 覆盖、原 LD_LIBRARY_PATH 与历史库 SHA；本包 `/run`/`/tmp` 路径均不存在，也无遗留 nvidia-smi 监控进程。

## 两个未通过项的解释

服务接入失败是本包临时路径选择错误：`/run` 的 `noexec` 与直接 loader 错误相符。不能据此判定新库媒体功能失效。原方案要求库使用经预检的独立 `/opt` 目录；`/run` 适合临时 systemd 覆盖，不适合本机上的可执行库映射。本包恢复后停止接入，没有修改挂载参数或重新试载。

AC4 的现场 FFmpeg demux/解码/重采样组合未完整输出。此前[准备报告](preparation_report.md)中显式拆分 150 个 payload、直接调用保存库输出完整 6 秒的证据仍成立；本轮只证明消费者组合的这条链路失败。故障具体落在 demux、parser 交互、官方组件组合或其他层仍 **UNKNOWN**，没有改固定补丁、核心或样本来掩盖失败。

## 密码窗口与本地适配

最初的两个预检窗口在本地触发模块 `[checked]` 类型错误，尚未启动 SSH/sudo 目标；第二次是适配器误用缓存导出入口。另一次服务窗口因完整 Base64 命令撑出屏幕被取消，尚未变更服务。每次重试均取得用户明确确认。

本包临时适配器保留既有 WPF `PasswordBox.SecurePassword`、原 secure pair/清理、stdin-only SSH 传输、FIFO 分层结果、输出上限和 GUI 前后 action digest 校验；仅适配当前 SSH 别名、显式安全整数转换及窗口显示。digest 增加 SSH 配置、适配器、UI 适配器和模块源码 SHA。窗口固定高度、摘要可读、技术详情折叠/滚动，密码框和按钮固定在底部；折叠/展开两种 WPF 渲染均验证按钮位于画面内。

没有修改全局安装 Skill 或其规范源，也没有保存秘密。临时工具只保留为本次私人追溯证据，不成为共享维护入口或一般 sudo 工具。

## 证据与收尾

必要私人证据位于忽略的 `artifacts/nas-trial-20261010/`：现场预检、独立编码/AC4 输出摘要、服务试用与恢复、启动错误、最终保护/清理及容器集合变化；窗口预览和退役到 `tools/` 的本包临时工具亦保留。没有保存私人影片、影片截图、私人路径日志或完整敏感 journal。

远端自建树 17 个文件、35,285,464 字节，以及一个 16,570,934 字节恢复归档，经文件集合、无链接/特殊文件、无活动消费者、当前基线和容器集合复核后清理；共 **18 文件、3 目录、51,856,398 字节**。本地 `remote_recovery.tar.gz` SHA256 `b938de6ec3938f2a8c840f2cd12096cf4eb240db5e647fb4c1c364ca87d65a46` 与远端原归档一致，包含该树完整的 17 文件，可恢复本包暂存材料。没有清理旧材料或其他远端路径，原 90 覆盖和可用库保留。

## 下一有限包与停止点

建议下一包：先在本地/只读证据中核对 AC4 的 packet 数、边界与错误策略，保持固定核心和制品不变；现场仅在另行批准的空闲窗口，经 `findmnt`/祖先路径/权限/依赖预检，将同一 run1 库放入独立 `/opt` 新目录，重复单服务 720p、跳转/继续及用户听感，最后恢复当时实际可用基线。不要放宽挂载安全选项，不重新枚举/长跑，不安装组件或重建候选。

本轮已停止。新库消费者接入、AC4 集成根因、full vendor parity、其他格式、原生 HEVC/HDR/字幕、并发、NAS 重启及长期稳定性分别保持未闭合；完整原版功能对等仍 FAIL。下一包需单独批准，不由本报告自动授权。
