# AC4 与升级部署工具本地交付

2026-10-10；来源用户消息 `01a124db-abaf-7ca1-b4e0-05c4ddd3f165` 的直接批准已读回。本包仅使用既有本地 WSL/Docker、固定材料和标准库，未连接 NAS、重启服务或启用开机任务。旧报告、候选、两份固定补丁及恢复包不改写。

## AC4 职责与合同

固定 FFmpeg 8.1.1 源包的 `libavformat/ac4dec.c` 承担 raw AC4 读包，原始文件 SHA256 `8c437a4cd32bcbe6b0698f06811b05da5206d9010a7d6a351c158d539f93b421`。厂商实际 libavformat 的完整对应源码仍缺失；其运行差异和本包上游复现方向一致，不能据此声称厂商组件已修复。

新增[demux 补丁](../patches/ac4_demux.patch)，不改旧 decoder/parser 补丁。可选的单个 leading ID3 v2.3/v2.4 revision 0，按 synchsafe 长度跳过完整标签；支持 v2.4 footer 并核对其内容，标签体限制 1 MiB。变换/扩展/实验及保留标志、其他版本拒绝，标签正文作为不透明元数据，不做内容语义验证。这是有界 envelope 合同，不是完整 ID3 实现。[ID3 v2.4 结构规范](https://id3.org/id3v2.4.0-structure)

同步字只接受 AC40/AC41；16-bit 长度或 FFFF 后的 24-bit 长度，长度不含封装头和 CRC，零长和短读拒绝。AC41 用 0x8005、初值 0、无反射/最终 XOR；CRC 覆盖长度字段（含扩展）和 payload，连同传输 CRC 必须零余数。坏包立即返回错误，不扫描重同步、不跳坏包、不使用固定偏移。[ETSI TS 103 190-1 V1.4.1 Annex G](https://www.etsi.org/deliver/etsi_ts/103100_103199/10319001/01.04.01_60/ts_10319001v010401p.pdf)

[严格 packet 驱动](../scripts/ac4_packet_probe.c)仅 clean EOF 且读到非空包时成功。[实验解码入口](../scripts/decode_ac4_checked.sh)先完整检查包，再以 `-xerror` 解码，错误非零退出并拒绝覆盖已有输出。普通 FFmpeg CLI 对部分读包错误可能仅写日志、仍返回 0；不能仅凭其退出码宣称通过，也不修改全局 CLI 错误政策。

## 构建、复现与正反例

私人证据根：`artifacts/local-delivery-20261010-01a124db/`。冻结 Docker 镜像与[既有构建报告](build_report.md)相同；新容器无网络、只读输入、cap-drop ALL/no-new-privileges、2 CPU/4 GiB，结束即移除。只启用必要 AC4、PCM/WAV、file、滤镜和 CLI，输出 libavformat/libavcodec 及所需配套库，**与单库部署组合分离**。使用[实验构建入口](../scripts/build_ac4_experiment.sh)，不修改固定镜像、不加入依赖。

第一次 `before` 编译完成但 probe 链接失败，材料保留；`before2` 修正版本库链接后完成。镜像没有 Python，最初测试 exit 127 不是 RED；使用已有 WSL Python 才取得真实 RED。原样 6 秒样本默认 CLI 输出 1 秒并报错，150 包身份检查及畸形输入合同共 23 个断言失败。没有用路径/工具失败冒充媒体失败。

修复后 `after`：原样输入默认自动识别 CLI 完整输出 6 秒，无 error 输出；严格驱动 150 包的 pos/size/payload SHA256 全部与独立逐帧 oracle 一致。CRC oracle 用独立逐 bit 算法及 `123456789 → FEE8` 固定向量。v2.3/v2.4、AC40/41、16/24 位、footer、无标签和 65536 字节 payload 正例，以及空输入、坏同步、长度/标签/CRC 截断、错误 CRC 覆盖、非法标志/版本、超限标签和后置垃圾等反例均纳入实际库测试。最终计数与制品身份见本包 `summary.json`，原始 stdout/stderr/机器结果保留。

CPU 输出仍为两声道 51.2 kHz；本包只关闭 raw demux/有界默认消费者，不改变解码器的采样率行为、不宣称 AC4 标准符合性或 NAS 通过。

新最小组合的构建声明 GPLv3+，没有启用 FDK/nonfree；源文件自身 LGPL 文本和旧补丁 GPLv3 约束保留。不将整项目许可重标，不分发驱动。实验库、合法测试小样本及本包证据仍私下保存在忽略的 artifacts，原完整单库仍是 nonfree/unredistributable。

## 部署工具设计与本地验证

普通入口[fnos-nvenc.sh](../fnos-nvenc.sh)，提供 check/deploy/status/rollback 四个动作；[中文短说明](quick_start.md)给出实际命令。控制器在[scripts/nvenc_runtime.py](../scripts/nvenc_runtime.py)，只有本机 Linux CLI，无 SSH、下载、安装、测试 root 选项或秘密输入处理。

[适用身份](runtime_profile.json)绑定 9 项官方文件、单元及 trim-media 的 SHA、Debian/glibc/架构/GPU/驱动、API 和 run1 单库。候选放在新的独立 `/opt/solis-fnos-nvenc/managed/<SHA>/`；原系统文件和旧 90 配置只读，工具只拥有 `/run/.../95-solis-nvenc-managed.conf`。候选目录可执行/可加载，不能用 noexec 的 /run 库目录。安装后重新核对 SHA 与加载能力；共享输入不读取旧 Codex 目录。

检查 ABI/SONAME、glibc 要求、完整动态依赖解析/身份及驱动 API；未知版本、未知依赖、坏制品、外来覆盖、符号链接、活动转码或恢复点漂移拒绝。已知官方组件的接口条件已满足时提示先用官方，接口条件不替代原生实测。状态分别报告安装、服务映射和转码 NOT_VERIFIED，普通输出不铺开技术哈希。

部署前冻结**当次**实际库、配置/环境摘要、文件 size/mode/uid/gid/SHA、依赖和 boot_id；仅保存非秘密 LD_LIBRARY_PATH 与环境 SHA，其他环境值不落盘。使用进程锁和原子配置/状态更新，重复同一已加载版本不重启。失败撤销本工具覆盖、重启 mediasrv 并核对当次基线；恢复也失败则写 recovery_required，停止并保留证据。再次部署保留上次恢复记录，不盲用升级前基线。回退到当次历史可用库的测试与官方基线测试分别覆盖。

[隔离测试](../tests/test_nvenc_runtime.py)使用真实 Linux 临时文件树，service/GPU/加载接口为测试替身；它不证明真实 systemd、NVIDIA 或 NAS 行为。正例、重复执行、未知版本/GPU/依赖、升级漂移、复制漂移、覆盖冲突、符号链接、空闲门、失败自动恢复/恢复失败、源 bundle 损坏后的回退与重启后新基线均验证，保留先失败后修复的结果。

私有 `artifacts/runtime_bundle/` 只装入已核对 run1 单库，并有来源/许可/身份回执；不带实验 libavformat。**NAS 工具现场验证为 false；完整外部依赖身份为 null，fnOS 产品版本号 UNKNOWN。运行变更入口明确 STOP。**这些需要下一次获批的 NAS 预检与隔离接入补齐，用户不自行改 profile 放行。

最终有 26 项 Linux 部署模拟通过，另有 AC4 7 项测试方法、37 次实际进程检查；150 包身份一致，原样默认/严格消费均完整 6 秒。最后补充已批准新版本 profile 的衔接：旧覆盖已撤销时只保留旧恢复记录，新部署冻结新基线；旧覆盖仍在或未知升级时拒绝，禁止重放旧基线。

最终实验构建入口另在 `after_final` 新目录真实执行，三程序和六种共享库（含版本文件）的 SHA 与 `after` 全部一致。当前构建入口自动记录脚本、probe 和新补丁 SHA；早先构建未包含这些自动字段，保留其实际记录，并通过 built_ac4dec 与生成补丁源码一致核对，不补造先验记录。

## 持久与重启恢复设计

本版仅临时覆盖：/run 配置随重启消失，/opt 库和 /var/lib 恢复记录保留；下一次部署重新检查并冻结当前基线。重启后不自动加载，也不拿上一 boot_id 的恢复点覆盖当前系统。状态可显示“安装了但未加载”，没有覆盖时回退返回 ALREADY_INACTIVE，不声称实际恢复演练。

若以后批准持久方案，只考虑带版本/依赖/boot 身份门的单服务启动单元；先检查再启用，未知升级直接停用兼容覆盖，记录新的有效恢复点。失败必须回到该次实际基线；禁止开机无条件复制旧库。设计尚未实现/安装，NAS 重启恢复及长期启用 NOT_VERIFIED。

## 交付边界与下一包

本地收尾：10 项固定材料和保存库身份、6 项既有 WAV 测试、110 个相关 Markdown 本地链接及语法/空白检查通过。新增 11 项必要共享文件与 6 项文档更新加入本地跟踪；没有提交、远端或推送。9 个本包临时工具共 22,499 字节，经精确路径/ReparsePoint/维护消费者检查后移入私人证据根 `tools/`，源/目标逐项 size/SHA 一致，未删除材料或清理历史目录。回执为 `tools_manifest.json` 与 `tools_retirement.json`；本包完成后停止。

本包只交付本地修复实验、工具和说明。真实 NAS 的工具部署/回退、libavformat 多库组合、AC4 实际厂商消费者与重启恢复未验证；厂商源码仍是生产修复缺口。完整原版功能对等 FAIL、其他格式/并发/长期稳定性 NOT_VERIFIED 继续保留，不扩大到全部警告或容器调查。

下一有限包建议：单独批准 NAS 只读版本/完整依赖/当前消费者绑定和升级后真实基线预检；通过后仅单服务运行工具的临时部署、原生有限验证、失败/正常回退及证据保全。实验多库 AC4 接入需明确批准扩大的组件组合与其恢复合同，不能沿用单库授权；重启恢复/长期启用再单独决定。
