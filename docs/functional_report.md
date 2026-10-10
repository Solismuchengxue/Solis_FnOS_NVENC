# 2026-10-09 本地 CPU 功能回归与编译警告排查

本文件保留该轮原始分类与边界。后续获批的 AC4 补测、4 项独立复核及完整入口结果见[2026-10-10 准备报告](preparation_report.md)；不改写本轮的 17 PASS/4 REVIEW/AC4 SKIP 历史记录。

## 结论与范围

21 个小型合成测试的新旧库解码退出均为 0，规范化像素/PCM 输出逐字节相同，未观察到崩溃、解码错误、空输出、非有限 PCM 或静音声道。功能指标分类为 **17 PASS、4 REVIEW、0 FAIL**；另列 **1 SKIP、3 NOT_VERIFIED**。这仅是所列 packet 输入上的 CPU 回归，不是全部格式、任意影片或内存安全通过。

来源会话 `[D60]Solis_Pvescript负责人` 的直接用户消息 `01a12133-6c47-7601-ad3b-5b95606cc7fc` 回复“同意”；已核对上一建议为“新库功能测试＋编译警告排查”，完成本地报告后停止。未来飞牛实测/回退建议没有获得本包授权。

正式输入沿用[构建报告](build_report.md)：新库 SHA256 `88e48674062ee5ef71864a2619324772bc856fec78c0d4793920fa7d4c15cd57`，历史候选 `3d7e7e241715fb6a3468a4d47d0fdaef3e6b79cecc3d3bb1f6d3118fac265367`。两份新库身份相同，实际测试 run1；run2 保留并核对身份，不宣称另做第二轮媒体测试。源包、补丁、旧/新库及冻结环境原样保留。

## 方法与直接证据

仍用已有 WSL2 / 本地 Docker 和冻结镜像 `sha256:168b5407fe9a839977f328d4e18f7c9e79dd596458a93f36a73de6e0e2b0bebc`。新容器无网络/GPU/端口/宿主 socket，输入只读，2 CPU / 4 GiB / 256 pids、cap-drop ALL、no-new-privileges。最终媒体测试为 UTC 15:25:23–15:26:34。

测试驱动只从固定 FFmpeg 8.1.1 源包构建同版本 libavutil/libswresample 和小型 C 探针，**没有重建 libavcodec、安装依赖、修改镜像或宿主能力**。辅助库不是 fnOS 官方依赖组合；本轮没有访问 NAS。

每个生成/解码进程使用 `dladdr(avcodec_version)`、真实路径解析、文件 SHA256 和 `/proc/self/maps` 确认加载身份。新库来自 `/input/artifacts/rebuild-20261009/run1/libavcodec.so.62`，对照来自 `/input/artifacts/candidate-lib/libavcodec.so.62`。故意给进程声明错误路径的测试在媒体处理前被拒绝，未产生输出；工具自带/系统其他 libavcodec 不能充当被测库。

自生成约两秒数学波形及 144×96 / 24 fps / 48 帧动态图，不引入外部/私人媒体。编码统一由保存的新库完成，同一 packet 输入分别由新旧库解码。`SCFIX3` 保存必要 codec 参数、声道 mask、FOURCC、extradata 和 packet；它是探针格式，不是 MP4/MKV/AVI/HLS。未测试 demux、播放器或跨轨同步，也没有独立标准解码器作全部格式的质量 oracle。

详细输入来源、每个输入 SHA256、尺寸、退出状态、帧/采样数、输出 SHA256、RMS/峰值、时长、逐声道指标与身份日志见忽略的[机器结果](../artifacts/functional-20261009/run/summary.json)和[执行记录](../artifacts/functional-20261009/run/execution.json)。工具二进制 SHA256 为 `5f6ac4505380b0bf176a669ca0f39ef0d6f9bb9fb1a9c790bba45713e7db7462`；源码/驱动身份随结果保存。输入、工具及 nonfree 库只供私人测试，不入 Git、不作为公开再分发发行物。

C 探针最终在 GCC `-Wall -Wextra -Werror` 下编译通过；10 个 Shell 文件在 Debian Bash 5.2.15 解析通过，Python 解析/编码检查通过。ShellCheck 不在冻结环境，`NOT_RUN`；这些检查不替代被测库的警告/运行风险排查。

## 通过、待核对与跳过清单

| 测试 | 项数 | 指标分类 | 直接观察 |
| --- | ---: | --- | --- |
| H264 / HEVC，含 B 帧 | 2 | PASS | 各 48 帧，144×96，像素相对自生成原始信号 PSNR 53.35 / 54.62 dB |
| AAC LC stereo / 5.1 | 2 | PASS | 48 kHz，各声道非静音，时长与两库输出一致 |
| AAC HE stereo，float / fixed decoder | 2 | PASS | SBR 样本解码成功，输出一致 |
| AAC HE mono | 1 | REVIEW | 两库均输出两个相同 440 Hz 声道；不同于输入的一声道 |
| AAC HEv2，float / fixed decoder | 2 | REVIEW | 输出一致且非静音；右声道预定基频能量占比约 0.558 |
| AC3 / EAC3，stereo / 5.1 | 4 | PASS | 48 kHz、2/6 声道，各声道非静音，输出一致 |
| DTS stereo | 1 | PASS | 输出一致，各声道非静音 |
| DTS 5.1(side) | 1 | REVIEW | 输出一致；LFE 60 Hz 基频能量占比约 0.572，RMS 约 0.0603 |
| WMA v1 / v2 | 2 | PASS | 解码成功、非静音，输出一致 |
| FFV1 / Ut Video / MagicYUV，8-bit YUV420 | 3 | PASS | 解码像素与原始合成像素完全一致；不覆盖 FFV1 float32 或 Ut Video 10-bit |
| MP3 | 1 | PASS | 解码成功、非静音，输出一致 |
| AC4 | 1 | SKIP | 保存库没有 AC4 encoder；本包未取得许可明确且适合当前探针的 elementary 输入，历史 AC4 短测没有重跑 |
| VVC scaled inter / FFV1 float32 remap / LCEVC BSF | 3 | NOT_VERIFIED | 没有对应有效输入/分支覆盖 |

音频输出 1.9627–2.1760 秒，含编码延迟/填充差异；未将其当作播放器同步证明。`REVIEW` 是需要解释的指标现象，不等于已确认核心库故障。初版用输入声道数相等及每声道基频能量 ≥0.65 作通用门，四项触发；该阈值不是 codec 标准判据，现保留原始数据与初轮判定，按待核对处理，没有降低阈值制造“全通过”。

固定源码 `libavcodec/aac/aacdec.c` 明确包含将 HE-AAC mono 作为 stereo 处理的分支；观察与该行为一致，但没有做分支插桩。HEv2 的参数立体声、DTS LFE 的编码/滤波可能影响纯音指标，这是待验证解释；尚不能归因为正确行为或缺陷。没有人工观看/听取，不宣称无花屏或听感正常。

## 33 条警告的归类与边界

两次保存的编译日志各 33 条、逐条诊断一致；精简分类和原始日志哈希在机器结果中，源码有界片段保存在私人证据目录。

| 固定源码位置 | 每次条数 | 涉及路径与排查结论 |
| --- | ---: | --- |
| `aacsbr_template.c:729`，stringop-overflow | 8 | float/fixed SBR。VARVAR 的 envelope 数有 ≤5 门，循环关系约束索引；这是源码约束观察，不是误报已证实。HE/HEv2 本次未观察到崩溃/输出新旧差异；具体 grid 分支、畸形流与内存安全未验证 |
| `wmadec.c:524`，stringop-overflow | 1 | WMA v1/v2 channel_coded。`ff_wma_init` 拒绝 >2 声道，block 内另有 assert；两种 stereo 样本成功。跨函数不变量可能解释 GCC 警告，但警告不关闭 |
| `vlc.c:443`，array-bounds | 3 | `add_level` 的 16-bit val16 索引；递归由 `max_symbols=6>>is16bit` 限制。固定源码调用追踪指向 Ut Video / MagicYUV，不能拿普通 AAC/WMA 的 VLC 测试当作此函数覆盖。两个 8-bit 样本成功，16-bit/10-bit 路径未验证 |
| `vvc/inter_template.c`，stack-usage | 18 | scaled inter 临时栈约 327,672–327,736 字节；无对应输入，没有验证实际线程栈余量/调用组合 |
| `ffv1enc.c:1404`，stack-usage | 1 | float32 remap 栈约 139,936 字节；YUV420 测试不经过该路径，仍未验证 |
| `bsf/extract_extradata.c:374`，discarded-qualifiers | 1 | LCEVC extradata 的零长度 dummy writer；本包没有调用对应 BSF，不把 H264 解码通过作为它的证据 |
| `ac4dec_data.h:447`，unused-variable | 1 | 补丁表未引用警告；它没有证明运行错误，也没有关闭 AC4 功能门 |

未改上游/补丁、未换版本，未运行 ASan/UBSan/模糊测试；现有被测二进制并未为这些工具插桩。没有确认警告导致本次崩溃或新旧差异，**所有内存边界/栈风险仍保留**。若要修复库或更换版本，需要独立有限包与原问题直接证据。

## 维护、清理与下一决定

复用入口和调用条件见[维护说明](maintenance.md)。新共享外层 wrapper 做 Linux Bash 解析和既有输出拒绝测试；本轮实际媒体运行使用临时 Docker 适配器，内部准备/回归步骤已真实执行，未再宣称新外层 wrapper 完整端到端重跑。

保留最终小型 fixtures、两库 raw 输出、身份日志、机器结果、辅助工具和必要源码片段。初轮 DTS layout、Ut Video FOURCC 失败与指标判定以[精简诊断](../artifacts/functional-20261009/probe_diagnostics.json)保留；白名单核对后清理本包 5 处临时树及 3 个废弃初轮元数据文件，共 389 文件，见[清理回执](../artifacts/functional-20261009/temporary_cleanup.json)。容器均 `--rm`，不删除镜像、卷、原材料、上一包环境缓存或回收站。

下一有限包建议先取得许可明确的 AC4 输入，并用适当独立参考解码/参数信令对照核对 HE mono、HEv2 和 DTS LFE 三类现象；再决定是否具备飞牛实测前提。本报告不启动该包、不授权现场接入。

完整厂商对应源码缺失、18 个缺注册项及 full vendor parity `FAIL` 仍未关闭；NVENC GPU、fnOS 依赖组合、播放器音画同步、真实回退/重启、未测格式与长期稳定性保持各自未验证，当前 NAS `UNKNOWN`。本包止于本地报告。
