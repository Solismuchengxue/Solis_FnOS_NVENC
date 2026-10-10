# 2026-10-10 飞牛临时实测前的本地准备报告

## 结论与本包边界

本地准备已完成，可以提交[飞牛临时实测方案](nas_trial_plan.md)审批。新增 AC4 的一个 6 秒官方测试片段在保存的新旧库中解码成功、PCM 字节相同；上一包 4 项 REVIEW 经独立实现对照，归类为 **原通用判据不适用**，没有确认这四项的核心解码缺陷。维护外层入口已真正端到端运行。

这不是全部格式、标准符合性或长期质量通过。33 条编译警告的内存边界/栈风险没有关闭，full vendor parity 仍 FAIL（缺 18 个注册名称），当前 NAS 状态 UNKNOWN。没有连接飞牛、修改消费者/服务/配置或演练恢复，也没有 commit/push/remote/GitHub 操作。

来源会话 `[D60]Solis_Pvescript负责人`（`01a089f2-db0d-7c42-88dc-9a1de7dfb1cb`）的直接用户消息 `01a12172-264a-75c0-965f-619ec87dd505` 批准合并本地准备包，已读回原消息和前一建议。范围为 AC4 合法小样本、4 项音频独立复核、必要警告检查、完整入口及统一收尾；取样或参考不足时记录缺口并继续其他工作。现场接入、核心库修复/升级和长期启用仍是独立决定。

## 固定输入与真正执行

被测对象沿用[构建报告](build_report.md)，实际每个进程再次核对真实库路径、SHA256 和 `/proc/self/maps`：

| 对象 | SHA256 / 身份 | 本包用途 |
| --- | --- | --- |
| 保存的新 run1 库 | `88e48674062ee5ef71864a2619324772bc856fec78c0d4793920fa7d4c15cd57` | 实际 CPU 编解码 |
| 保存的新 run2 库 | 与 run1 相同 | 身份读回；没有声称独立媒体运行 |
| 历史候选库 | `3d7e7e241715fb6a3468a4d47d0fdaef3e6b79cecc3d3bb1f6d3118fac265367` | 相同输入的回归对照 |
| 固定环境 | `sha256:168b5407fe9a839977f328d4e18f7c9e79dd596458a93f36a73de6e0e2b0bebc` | 原镜像未修改 |

现有 WSL2 / Docker 29.7.2、本地 UNIX socket；媒体与参考执行容器使用无网络、只读项目输入、cap-drop ALL 和 no-new-privileges。只在新的隔离参考准备容器下载小型 Debian 官方包，没有安装宿主依赖。固定 FFmpeg/补丁、候选库、冻结镜像和原环境归档保持原样；只构建同版本 libavutil/libswresample 与诊断驱动，**没有另编译 libavcodec 作为测试对象**。

`test_codecs_isolated.sh` 的最终版本完成新准备容器、第二个测试容器及结果整理，21 项实际解码/比对仍为 17 PASS、4 REVIEW、0 FAIL；这些基础分类原样保留，独立复核由下一节补充。实际最终输入、进程日志、工具身份与机器结果在忽略的[完整入口结果](../artifacts/preparation-20261010/run_verified/summary.json)。错误库身份拒绝门仍通过。初轮和中间运行的有效摘要保留，重复大输出在核对后清理。

## 4 项 REVIEW 的独立复核

FDK AAC 2.0.2-1 与 VideoLAN libdca 0.0.7-2 直接解码同一 packet 输入；参考进程没有映射 libavcodec/libavutil。两份 libdca 包从冻结环境已验证的 Debian 官方索引取得，共 185,340 字节，下载 SHA256 与索引一致，只在新容器解包。实际参考库 SHA256：

- FDK：`0a9d97e386108d1ac1460fdf2d290143b228d69e4d7c985b80a6a32258d66998`。
- libdca：`cd89a0eb3870e2f3745a616a66c830d223642f709795ed5aeedb73a2df616f7d`。

共 9 个参考案例含 AAC LC stereo/5.1、HE stereo float/fixed 和 DTS stereo 控制项，均退出 0。声道顺序按各库接口明确处理；DTS 3F2R+LFE 的 planar C,L,R,SL,SR,LFE 映射为 L,R,C,LFE,SL,SR。参考 SHA、许可、包元数据和小型源码留在私人材料目录；GPL-2+ 的 libdca 和 FDK 自身条款不被项目统一改标为 MIT。参考介绍和接口来源为 [VideoLAN](https://www.videolan.org/developers/libdca.html)、[FDK 2.0.2 API](https://raw.githubusercontent.com/mstorsjo/fdk-aac/v2.0.2/libAACdec/include/aacdecoder_lib.h)。

对照使用一个每案例共同的有限时延搜索（±4096 samples），全部得到 0；取中间一秒，不做逐声道时移、增益校正或重采样。已用 3 个已知随机信号偏移核对时延算法。NumPy 使用本机已有版本，未安装新宿主包。数字和身份见[参考机器结果](../artifacts/preparation-20261010/reference_run_final/summary.json)。

| 原 REVIEW | 独立直接观察 | 有界分类 |
| --- | --- | --- |
| HE-AAC mono | FDK 同样输出两个相同 440 Hz 声道；与 native 的最低相关系数 0.9999999962、最大归一化 RMSE 0.0000887；固定 FFmpeg 的 mono-as-stereo 分支已有记录 | 对这个输入，输入/输出声道数必须相等的门不适用；不是新库回归 |
| HEv2 native | 右声道基频占比 native 0.5579690、FDK 0.5579720；最低相关 0.9999999627、最大归一化 RMSE 0.0002739 | 原纯音 ≥0.65 不是该输入的正确性 oracle；没有确认独立于参考的偏差 |
| HEv2 fixed | 与同一 FDK 输出最低相关 0.9999999797、最大归一化 RMSE 0.0003361 | 同上，保留原始值而不降低阈值制造通过 |
| DTS LFE | 60 Hz 占比 native 0.57244780、libdca 0.57244785；LFE RMS 0.06025221 / 0.06025224；全声道最低相关 0.9999999981 | 低音现象也存在于独立实现，原纯音门不适用；没有确认 decoder 特有错误 |

独立实现对照比“两个 FFmpeg 一样”增加了证据，但不是认证标准解码器。AAC 输入编码器与 FDK 参考来自同一实现家族；本次仅稳态 PCM，没有参考尾部 flush、听感、任意流或 ISO/ETSI 符合性结论。HEv2 的参数立体声及 DTS LFE 编码/滤波对指标的影响是合理解释，本包不宣称完整机制或编码器质量已被证明。上一包原始观察与分类仍在[功能报告](functional_report.md)。

## AC4 小样本、许可与结果

仅下载 Dolby [官方 Mobile tests](https://ott.dolby.com/Mobile_tests/index.html) 中 packed audio 清单的首个 6 秒片段，未取整套 SDK、20 MB 视频或历史/私人媒体。[Dolby 测试说明](https://professionalsupport.dolby.com/s/article/Endpoint-Device-Testing-for-Streaming-Services)链接该入口，并限定测试向量用于测试；完整页面直读超时，已由官方搜索索引读取该说明及入口关联。本材料只作本地私人验证，不认为有公开再分发权。

| 材料/结果 | 身份或直接值 |
| --- | --- |
| 官方片段 | [channel_check_IMS_audio_id3_sub_0000.ac4](https://ott.dolby.com/Mobile_tests/HLSv4_ac4/channel_check_IMS_audio_id3_sub_0000.ac4)，86,733 字节 |
| 原始 SHA256 | `2c1b726a9d9bd08afd6d10a42d2933ae69b27ec8f0842d9476d2bcdb48f4c533` |
| 分帧 | 73 字节 leading ID3、150 个完整 AC4 payload；另一 Python 边界检查逐 packet 核对 fixture 字节 |
| 两库解码 | 各 150 frames、307,200 samples/声道、2 声道、51,200 Hz，时长恰 6.0 秒 |
| 输出 | 全部有限 PCM，RMS 0.0730151、峰值 0.364046；两声道 RMS 0.0722067 / 0.0738146，无静音声道 |
| 两库相同输出 SHA256 | `65e2aad6c8f6d593e1ef6d638ad4c8c200f04dd0f38e80dc515d7d2a72405ccc` |

状态 **PASS_LOCAL_DECODE_AND_REGRESSION**，详细记录见[AC4 结果](../artifacts/preparation-20261010/ac4_run_verified/summary.json)，来源/使用条件/哈希见[样本来源记录](../artifacts/preparation-20261010/provenance.json)。输出 51.2 kHz 是直接观察；没有测试向 48 kHz 的重采样及 fnOS 消费者处理，不从 6 秒正确时长推导采样率兼容或听感。

首轮把整段直接交给补丁 parser，误得 1 packet、两库拒绝。源码明确该 parser 只分析 packet；驱动已按固定上游 raw demuxer 规则处理 ID3、sync、16/24-bit 长度及 CRC 占位，再逐 payload 分析，得到完整 150 packet。初轮属于测试适配错误，其失败不用于宣称 AC4 核心缺陷；保留[诊断记录](../artifacts/preparation-20261010/diagnostics.json)。本包没有改核心源码或补丁。

这个 IMS 片段没有独立 AC4 解码器或已知完整 PCM oracle。对象编码、其他 presentation/声道模式、多段切换、畸形流、容器 demux、播放器和全部 AC4 仍未验证；原补丁的未实现分支继续保留。

## 警告与本地收尾

原两份日志各 33 条诊断及分类未变，已由本次完整入口结果再次读取。AAC SBR float/fixed 的本次输出与 FDK 接近，WMA v1/v2 和 Ut Video/MagicYUV 8-bit 有重新执行证据；这只能缩小所列有效短输入的功能疑虑，不证明触发警告的具体分支覆盖或内存安全。VVC scaled inter、FFV1 float32 remap、LCEVC BSF、Ut Video 10-bit/16-bit 和畸形输入仍 NOT_VERIFIED。未跑 ASan/UBSan/FATE/模糊测试，也没有为清零警告重建/升级核心库。

最终 C 驱动使用 GCC `-Wall -Wextra -Werror` 编译；12 个 Shell 在 Debian Bash 5.2.15 解析通过、6 个 Python AST/编码和 68 项本地 Markdown 链接通过，AC4 无效/截断输入及既有输出拒绝门通过。ShellCheck 不可用，NOT_RUN。材料身份与 Git 空白/跟踪范围已核对。必要源码、报告和计划加入本地跟踪，样本/缓存/工具/PCM 仍被忽略。当前包自建临时文件和重复输出在白名单及无 ReparsePoint 检查后清理，共 443 文件、101,461,727 字节；必要证据和上一包材料保留，清理/环境读回见[本包收尾记录](../artifacts/preparation-20261010/closeout.json)。

## 剩余缺口与下一有限包

本地 AC4 缺样本和这四项指标解释的缺口已得到本包所述有界补充；未测模式与标准认证没有关闭。现场阻断项是 SSH 目标/权限、当前消费者和依赖身份、当前可用版本恢复点、空闲窗口与所选合法输入，均须在获批包的只读预检中确认；未知或不匹配时停止变更。

下一包只提议临时 GPU 转码、原生播放/跳转/继续、必要音频处理与恢复当前可用版本，具体精确边界见[现场方案](nas_trial_plan.md)。本报告完成后停止，等待用户批准该现场包；不因本地准备完成而自动执行。
