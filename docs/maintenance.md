# 维护条件与验证入口

本项目保存固定维护材料。只读材料校验和合成 WAV 单元测试可以在本地运行；构建、安装、回退执行和服务变更仍需各自的授权。历史结果与本轮验证分开记录。

## 公开安装器维护

当前 SSH 菜单使用 Python 3.11+ 标准库，公开入口及安装/暂停/卸载见 [README](../README.md)，新实现的分层结论见[安装器报告](installer_report.md)。下文“私人安装材料”“升级工具”等记录描述此前有限私人包，不是新公开入口的前提。

公开构建由 `nvenc_build.py` 固定下载、SHA256/签名和包版本，在当前 Linux 的本地 Docker 内准备依赖并双构建。输入是仓库、[公开来源清单](build_sources.json)和公开网络；不使用历史镜像 ID 或候选库。286 项 Debian 包依赖由签名的 snapshot 索引验证，只放宽固定历史 Release 的有效期限。产物和新环境镜像仍是本地受限制品，不公开分发。

本地相称验证：`python3 -B -m unittest discover -s tests -p 'test_nvenc_*.py'`，以及既有 runtime_files / WAV / consumer 测试。不要无条件 discover 全部 tests：AC4 集成入口需要明确 bin/sample/output。隔离根的 fake service 测试只证明安装事务和文件行为；systemd 的实际环境时序、整机重启、原生映射和听感由 NAS 有限验收关闭。

安装器采用 root 所有版本目录、普通原子 JSON 指针及独立持久 96 drop-in；每次启动先清空自己的环境，验证成功并落盘本 boot 恢复点后才注入。故障恢复按 state 路由，即使 hook 已移除也不能误报恢复完成。组件变化或 boot 不符时只撤销自有配置，不重放旧记录、不重启未知组合，明确恢复未验证。

更新从经核对的新源码入口进行，保留上一版和失败目录；当前损坏可由源码 `restore-tool` 独立验证上一版后恢复指针。卸载先验证文件、权限和消费者，自有新建库有单独所有权记录，既有历史库不认领、不删除。恢复记录、源码、旧工具备份和构建材料默认保留，无自动清理。

## 历史归档材料的本地验证

下列 `verify_materials.py` 需要维护者已保存的私人归档材料，包括 `artifacts/sources`；公开 Git 克隆不含这些材料，不能直接运行该归档校验器，也不需要以它作为安装前提。公开克隆的验证入口是上文 `test_nvenc_*.py`，源码获取与构建使用公开菜单。历史归档校验使用 Python 3.12+，仅使用标准库：

```powershell
python -B scripts/verify_materials.py
python -B tests/test_wav_check.py
```

材料校验覆盖[清单](materials.json)中的大小/SHA256，以及[历史检查](historical_checks.json)的计数和失败限制。它不重新执行 48 项媒体短测。WAV 检查器沿用已保存实现，验证 16-bit PCM、扩展多声道、非静音、时长和对照波形；六个单元测试只生成约半秒合成音频，不使用影片。

`tests/test_runtime_files.sh` 只测试单个覆盖文件的保护函数，调用者必须传入一个空的本地临时目录。它不访问 SSH 或 systemd。真实符号链接不可用时该项明确 SKIP，不能称为完整目标 Linux 通过。测试文件由调用者在核对目录边界后清理。

Shell 文件要求 Bash、UTF-8/LF。Windows 本地 Bash 解析通过只证明本地解析，不替代飞牛兼容性与真实执行。

## 构建核心与缺口

`scripts/build_libavcodec.sh` 合并了第二版两阶段构建的核心步骤：核对固定源包/补丁哈希和签名，安装本次构建专用 API12.1 头文件到输出前缀，按原补丁后单行修正的顺序应用，用 `--fatal-warnings` 和 AC-4 parser/decoder 双注册门禁构建，只复制 `libavcodec.so.62` 到候选目录。解包不恢复归档 UID/GID，支持本轮移除 capabilities 的新容器；不改变源码字节。

它需要调用者明确提供源码包目录、补丁目录和不存在的输出目录；在准备好的隔离 Linux 环境中执行。脚本不下载、不运行 apt、不提供容器启动器，不写官方影视库或服务配置。失败产生的输出只留在调用者声明的目录，不能作为成功制品。

历史基线：Debian 12 / x86_64，GCC 12.2、glibc 2.36；镜像记录为 `debian@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587`。完整历史包版本见[包清单](build_packages.txt)。核心依赖包括 build-essential、pkg-config、nasm、xz-utils、GnuPG、Git、libx264/libx265/libvpx/libwebp/libopus/libmp3lame/libvorbis/libtheora/libzvbi/libdav1d/libsvtav1/libfdk-aac/libdrm/libva/libvpl 的开发包；SVT-AV1 需要 encoder 开发包，不能只靠 common headers。

2026-10-09 有限本地构建包已完成冻结环境、依赖身份及真实 Debian 编译，两次字节一致与局部比较见[构建报告](build_report.md)。目前仍缺厂商完整对应源码、完整样本/许可范围、AC4 默认消费者兼容及恢复官方组件的真实回退。新库普通影片单路 720p、跳转/继续、听感及恢复历史可用版本已有[后续现场证据](nas_followup_report.md)，不覆盖其他格式或长期稳定性。两次构建观察不代表任意环境/未来版本都可复现。

## 隔离入口与冻结环境

需要已取得当次构建授权、现有本地 Linux Docker、完整私人材料及报告中的冻结镜像 ID。从本地 WSL/Linux 调用：

```bash
bash scripts/rebuild_isolated.sh "$PROJECT_ROOT" "$NEW_EXPORT_DIR" "$FROZEN_IMAGE_ID"
```

三个参数分别为项目绝对目录、尚不存在且父目录已存在的输出目录、冻结镜像 SHA256 ID。入口固定本地 UNIX Docker socket，核对引擎内核和镜像身份；使用新容器、只读输入和无网络构建，结束即移除容器。`run_clean_build.sh` 在其内部调用构建核心，再记录版本、源码输入哈希、ELF/codec 信息与文件保护测试，不处理媒体、不接入服务。

缓存文件大小/SHA256、镜像 ID 和读取验证见构建报告。恢复缓存前先核对报告中的归档 SHA256，再用现有本地 Docker 读取：

```bash
set -euo pipefail
gzip -dc -- "$ENVIRONMENT_ARCHIVE" | docker --host unix:///var/run/docker.sock load
```

加载后核对镜像 ID 与报告一致，再调用构建入口；不要只信任可变 tag。重新准备环境时，在固定基础镜像的全新具名容器内只读挂载项目，并提供空的独立记录目录，调用 `prepare_build_environment.sh PACKAGE_LIST EXPORT_DIR`。它仅支持 Debian 12/amd64 新容器，按历史清单精确安装，记录签名索引/下载哈希/版权；任何版本缺失或实际包清单差异均失败。`--record-existing` 只在已准备容器中补记元数据，不能关闭版本门。之后以本轮专属镜像身份冻结并导出，不得修改已有消费者或复用不明容器。

隔离构建包已停止于构建报告；随后获批的 CPU 测试包见下节。NAS 接入、真实回退和长期启用须另行决定。

## 保存库的 CPU 功能回归

前轮结果以[功能报告](functional_report.md)为权威，后续 AC4、独立参考及完整入口以[准备报告](preparation_report.md)为权威。不会以新编译的 libavcodec 替换被测对象。需要当次测试授权、已有冻结镜像和完整私人材料；在本地 WSL/Linux 使用不存在的独立输出目录：

```bash
bash scripts/test_codecs_isolated.sh "$PROJECT_ROOT" "$NEW_EXPORT_DIR" "$FROZEN_IMAGE_ID"
```

外层入口固定本地 socket/镜像身份，先在新容器用 `prepare_codec_probe.sh` 只编译固定同版本辅助库和 C 驱动，再用 `run_codec_regression.sh` 在另一个新容器生成小型信号并分别加载保存的新旧库。无网络/GPU、输入只读；不准备 NAS 或修改镜像。不复用已有输出；失败的目录不能称通过。

媒体步骤结束后，从项目根用 Python 3.12+ 标准库读取结果：

```powershell
python -B scripts/summarize_codec_regression.py . artifacts/your_authorized_test_output
```

报告区分 PASS、REVIEW、FAIL 和跳过。返回 0 仅表示无执行/比对失败；REVIEW 仍须阅读机器结果，不能称“全通过”。`SCFIX3` 是本地 probe packet 格式，覆盖 CPU codec，不测试 demux/播放器。样本、工具二进制、raw 输出与日志保持忽略；没有私人库的 Git 副本无法执行。2026-10-10 准备包已用最终驱动真正执行完整外层 wrapper，证据见准备报告。

已确认当次样本来源/测试用途与 SHA、参考包身份/许可后，可在新无网络本地容器内调用下列内部步骤；不在 WSL/宿主直接安装依赖。参数路径必须是显式绑定的只读输入及空的独立输出。

```bash
bash scripts/run_ac4_probe.sh "$PROJECT_ROOT" "$TEST_RUN" "$LEGAL_SMALL_AC4_SAMPLE" "$EMPTY_AC4_OUTPUT"
bash scripts/run_audio_references.sh "$PROJECT_ROOT" "$TEST_RUN" "$VERIFIED_REFERENCE_MATERIALS" "$EMPTY_REFERENCE_OUTPUT"
```

AC4 导入模式只支持小于 1 MiB 的 raw sync frame、可选无标志 leading ID3、16/24-bit frame size 和 CRC 占位；不是通用媒体 demuxer。独立参考材料是已核对的 libdca 开发头/库及已有 FDK SDK；参考进程拒绝 FFmpeg 映射，记录真实参考路径，调用前后另核对库 SHA。准备这些材料仍须当次授权，不改冻结环境。

后续[包边界诊断](nas_followup_report.md)确认本例官方默认 raw AC4 读取从 leading ID3 起点形成错误首包；完整 payload 解码和单变量读取偏移对照均为 6 秒。原始默认消费者仍失败。偏移 73 只是该样本的诊断值，不成为通用维护参数；实际读包合同修复须另行授权。

随后获批的[本地交付包](local_delivery_report.md)已在固定上游 libavformat 层复现并修复 raw 读包，原样输入完整 6 秒、150 包身份及严格错误退出通过。旧库/旧报告保持原样；厂商对应源码缺失，所以生产 AC4 仍未关闭。新增补丁是 `patches/ac4_demux.patch`；`build_ac4_experiment.sh ROOT EMPTY_EXPORT before|after` 只在现有冻结 Docker 新容器内部编译最小实验组合，配套库和 CLI 不加入单库运行包。固定镜像无 Python，测试用已有 WSL Python，不安装依赖。

开发者在已有本地 Linux、授权范围内用新输出执行实际库测试（将三个路径换为已绑定的本包输入/输出）：

```bash
LD_LIBRARY_PATH="$EXPERIMENT_LIB" python3 -B tests/test_ac4_demux.py --bin "$EXPERIMENT_BIN" --sample "$VERIFIED_AC4_SAMPLE" --output "$NEW_TEST_OUTPUT"
python3 -B tests/test_nvenc_runtime.py
python3 -B tests/test_nvenc_consumers.py
```

第一项真实消费实验库和 CLI，不是 parser 静态替代；第二项只操作 Linux 临时树，service/GPU/loader 是测试替身，不能当 NAS 通过。共享实验消费入口 `decode_ac4_checked.sh BUILT_BIN INPUT NEW_WAV` 先严格读包再使用 `-xerror`；任何错误退出非零，拒绝覆盖已有输出。

结果读取：

```powershell
python -B scripts/summarize_ac4_probe.py . artifacts/your_ac4_sample.ac4 artifacts/your_ac4_output 6
python -B scripts/summarize_audio_references.py . artifacts/your_test_run artifacts/your_reference_output
```

第一项用标准库独立核对 raw/fixture packet 字节、明确给出的预期时长、被测库身份和 PCM；第二项要求调用环境已具备 NumPy，输出有限时延、稳态指标与独立实现差异，不自动判定标准符合性。参考不做尾部 flush；实际当前案例时延均 0。不得把库间相似或成功退出当作主观音质/长期稳定性证据。

## 许可与保存

- FFmpeg 源包包含自身 LICENSE.md 与 COPYING 文本；两份补丁保留来源、字节身份和 GPLv3 构建约束，GPLv3 文本随补丁保留在[许可证文件](../patches/COPYING.GPLv3)。不把整个项目统一标为 MIT。
- AC-4 补丁部分文件头同时存在 public-domain 语句和 GPLv3+ 文本；本项目保留原样，并遵循其明确 GPLv3 配置要求。对象编码和部分声道模式仍有未实现分支。
- NVIDIA 接口头文件有自身许可声明，范围只及对应头文件，不授权分发驱动。
- 现候选启用 GPL/version3/nonfree/FDK AAC，构建声明 `nonfree and unredistributable`。源码包与候选库仅本地私人保存于忽略的 `artifacts/`，不得把该库上传或当可公开再分发发行物。
- 任务来源校验/回退代码尚未指定独立再分发许可；公开发布前需另行明确。公开测试样本不因 URL 可访问而自动获得再分发许可；旧试验媒体不收纳，新包必要小型合成 fixtures 仅按功能报告保存于忽略的私人证据目录。

FFmpeg 原文：[8.1.1 LICENSE.md](https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.1.1/LICENSE.md)。材料再分发与 NVIDIA 驱动、运行 License 是不同问题，本轮不操作后两者。

## 回退支持边界

`scripts/runtime_files.sh` 保留原文件保护：只移动指定的单个覆盖，拒绝内容漂移、符号链接和已有目标。`scripts/rollback_runtime.sh` 针对已知 `/run` mediasrv 覆盖与独立 `/opt/solis-fnos-nvenc/ffmpeg-8.1.1-api12.1` 前缀，要求调用者提供现场确认的单元及覆盖 SHA256。它不固化旧 PID、不带 SSH 地址或密钥参数；helper 从脚本所在目录加载。

真实执行会调用 daemon-reload 并重启 mediasrv，随后核对官方库映射及候选不再加载。该共享脚本只做本地静态验证，未在 NAS 执行，也未替换 NAS 已存回退脚本。恢复官方组件及重启恢复仍未验证；本轮恢复历史可用版本的直接结果以现场报告为准。

现场试用的恢复目标是实际当前可用版本，未必是官方库；该脚本只有合同一致时才能复用。精确的预检、临时覆盖及恢复边界见[方案](nas_trial_plan.md)，首次结果见[现场报告](nas_trial_report.md)，正确 `/opt` 路径的有限复测及恢复见[后续报告](nas_followup_report.md)。预检必须核对库目录挂载与映射权限，`noexec` 的 `/run` 不适合加载库；本次结束后的新复测仍需另行批准。

## 历史临时工具维护（新公开入口见上文）

普通用户只使用[短说明](quick_start.md)中的 `fnos-nvenc.sh`；旧 rollback_runtime 的手工 SHA 合同保留为历史支持，不能替代当次实际基线。新控制器沿用单项覆盖保护原则，自动冻结当次恢复点，不直接调用只面向官方恢复目标的旧脚本。

单库工具现场包的试用合同单独位于私人包 `artifacts/runtime_bundle/trial_authorization.json`，要求 root/0600、当次授权 ID、完整 profile 摘要、当前 boot、最长一小时的有效期和实际恢复点。只有一个 deploy/rollback 周期；结束后不能重放。`nas_tool_verified=false` 本身仍拒绝普通部署，试用不把授权当作通过事实。控制器等待 systemd 重启后的实际 codec 映射就绪，再判断加载；依赖冻结包含动态 loader，NVIDIA 动态加载文件另按保护文件核对。上一包短时外部恢复保护与阻断见[历史工具报告](nas_tool_report.md)；新的单路原生闭环、正常恢复、消费者修正与精准收尾见[完成报告](completion_report.md)。

`docs/runtime_profile.json` 是工具的明确适用合同，不是任意升级白名单。`artifacts/runtime_bundle/` 原样复制 run1，并核对源/目标 SHA，许可保持 nonfree/unredistributable 私人保存；不依赖旧 Codex 工件目录，不自动下载或编译。本轮已绑定 fnOS 1.2.0701、50 项实际 LDD 依赖（含 loader）及 13 项保护文件；新一轮部署/状态/回退、原生 720p、一次跳转/继续及本次声音确认通过，`nas_tool_verified=true` 仅开放已验证组合的普通入口。当前影片的转码验证仍由人确认，工具不自动判定。只有负责人在新的实际证据和授权范围内更新，不让普通用户改标记绕过。

本版不装 /etc 覆盖或开机任务；/run 临时配置随重启消失，重新检查后冻结新基线。重启与持久方案见本地交付报告，真实 NAS 验证/恢复/长期启用保持独立门。

## 历史私人安装材料与外部依赖

当前交付为 `artifacts/private_tool-20261010-delivery-v2.zip` 和外置 `.zip.sha256`，旧包保留。包内具备独立路径布局：入口、未变的 Python 控制器、runtime_profile、run1 单库和 identity.json、中文使用说明、修正后的完成报告、NOTICE、GPLv3 文本、manifest.json 与 SHA256SUMS。控制器只从安装根相对读取 docs 与 artifacts/runtime_bundle，不依赖旧工件目录、构建缓存或一次性 SSH 工具。包内 README 与依赖清单为生成材料；完成报告中的未收纳审计链接改成正式项目路径说明，事实正文与 SHA 修正保留；manifest 保存每项来源和转换说明。

| 材料或依赖 | 来源与要求 | 本包状态 |
| --- | --- | --- |
| wrapper、控制器、身份合同、run1 | 正式项目文件；按 SHA256 原样收纳 | 包内实际文件；核心字节不变 |
| 库的许可/身份、GPLv3 文本 | 已保存的许可声明和 patches/COPYING.GPLv3；不赋予整包统一许可 | 包内 NOTICE、identity 与许可全文 |
| Bash、Python 3 标准库、systemctl、readelf、ldd、nvidia-smi | 目标 NAS 现有命令和环境，须可运行本工具 | 不捆绑、不安装；前轮工具调用已通过，本轮不现场复核 |
| sudo、sha256sum、install、cp、find、chmod、chown | 首装命令的目标侧前提；journalctl 仅用于可选查看 | 未在本轮 NAS 核验；不存在则停止，不自动安装 |
| 50 项 loader/外部库、13 项官方/驱动保护文件 | runtime_profile 的路径与 SHA256；首次 check 实际核对 | 仅身份清单，文件由 NAS 提供 |
| NVIDIA 驱动、Toolkit、License、官方影视程序 | 现有目标环境与其原供应渠道 | 未收纳，不属安装材料补齐范围 |
| 固定源码、补丁、环境缓存及 AC4 实验多库 | 正式项目的构建/实验材料，职责不同 | 不装入私人单库运行包；不要求运行时重建 |

第一步材料安装只建立新的 `/opt/solis-fnos-nvenc/tool`（root，目录 0700 / 文件 0600），不重启服务；精确命令见[使用说明](quick_start.md)。权限是项目选择，不是厂商要求。既有工具目录不被覆盖；既有 state、旧 90、managed 或官方文件不在复制操作内。后续 deploy 才复制 managed 候选、冻结恢复点并设置自己的 95 临时覆盖。新包未在 NAS 实际首装，安装材料完整不等于空白 NAS 已验收。

版本渠道是所有者本地私人包及其 SHA256，无公开发行、无 remote/clone URL、无镜像。更新触发是用户在系统/影视升级后手动 check；未知组件/依赖停止。更换正式工具版本不是将新版 ZIP 强行覆盖旧目录，本包未实现该操作，也未授予 NAS 安装/更换权限。

## 历史 FNOS 标准例外登记

已通读 `F:\50_Relationships_and_Data\prompt_engineering\prompt_library\docs\fnos-project-standard.md`（2026-09-29 v1）；该跨项目标准未修改。本次来源人批准的四项交付包包含本项目原生影视目录与非 Docker 例外登记。下表只适用于当前单库方案，不推广为组织通用例外，不由文档登记推导现场验收通过。

| 标准条款 | 当前采用/差异登记 | 验证或剩余边界 |
| --- | --- | --- |
| §1 根目录与持久状态 | 后续部署材料在 `/vol1/1000/Solis_FnOS_NVENC` 下独立展开；安装运行位置例外保留 `/opt/solis-fnos-nvenc/tool`、`managed/<sha256>/`、历史 candidate-lib；恢复状态 `/var/lib/solis-fnos-nvenc/` | 用户已约定交付材料位置；尚未现场建目录，运行路径不迁移 |
| §1/§2 私人材料与从零入口 | Git 不含制品/秘密；许可受限库采用所有者私人 ZIP + SHA256，实际材料另供。当前无 HEAD/remote，Git-only clone 不具备运行材料 | 登记交付例外；本地独立解压身份核验，NAS 全新首装 NOT_VERIFIED |
| §2/§3 Compose 与命名 | 原生 mediasrv 单服务辅助工具，Python 标准库在 NAS 执行；不创建 docker-compose.yml、Compose 项目、网络或卷 | 本项目非 Docker 例外；Compose UI/SSH 两入口验收不适用；文件管理上传不称 Compose 部署通过 |
| §4 版本/更新/回退 | 无运行镜像；固定兼容包因 API12.1/R535 约束。先 check，未知停止；回退以当次实际库、配置、依赖和 boot 为合同 | 已知组合历史有限部署/回退通过；未知升级、跨 boot 恢复未验证；不新增自动更新 |
| §5 网络/认证/常驻配置 | 无独立网络、端口、账号、时区、restart 或容器资源设置；沿用原生飞牛入口和用户现有 WireGuard/认证。root 操作保护路径及 mediasrv 重启 | 固定组件身份与有限原生流程有前轮证据；当前地址/端口和网络未重新核验，不称上游镜像要求 |
| §6 日志 | 本工具 stdout/stderr 到终端，无追加文件日志，故没有文件轮转/自动保留任务；手动留存短输出。state/history 默认保留作恢复证据 | 官方日志继续默认；实际 journald 路由、应用文件位置/轮转/保留权限 UNCONFIRMED，不能承诺日志完整 |
| §7 临时文件 | 本地自建脚本在根 tmp/ 并忽略，无自动清理；既有 `/run` 95 覆盖、lock 和状态 `.new` 使用原位置；后续经授权的远端临时路径按当次合同 | 本项目运行临时路径例外；原子替换属于 §7 已允许行为；不以采用标准清理既有路径 |
| §8/§9 文档与验收 | README、使用说明、许可/依赖/权限、版本与回退、日志/空间以及本表已同步；详细当前交付见报告 | 本地材料检查与历史运行分层，未称整个标准 PASS 或独立 ACCEPTED |

日志和空间：工具无无限追加的文件日志；手动保存提示自行管理。state.json、previous-*.json、retired-*.conf 默认保留、无自动清理/轮转，升级次数增加会累积。managed 候选、旧 ZIP/解压副本也会累积；本包 ZIP 约 7 MiB、解压约 16 MiB、单个 managed 库约 16 MiB，目标剩余空间 UNKNOWN。系统/官方日志若未配置限制可能持续增长，位置、策略和手动清理方式未核实；只提供有 journalctl 时的近期查看命令，不在本轮修改或清理。本地 tmp/ 后续手动处理，正式制品和恢复证据不当临时文件回收。

后续由负责人部署时，交付材料目录固定为用户指定的 `/vol1/1000/Solis_FnOS_NVENC`，在其下使用未占用的版本目录展开并核对 ZIP/包内材料。临时输送与可丢弃中间文件放该项目 tmp/，不自动清理。校验后再安装到 `/opt/solis-fnos-nvenc/tool`，因此交付卷的挂载属性不被当作运行库可加载的保证；实际 `/opt` 目录的读取/映射权限仍须现场检查。用户未要求迁移 managed 库、恢复记录或官方组件。

当前 quick_start 中的首装命令通过 `test ! -e "$target"` 明确拒绝已有工具目录。既有 NAS 已安装工具，下一包需要先补安全更换/重装流程：核对新旧材料身份，保留可恢复旧工具，处理已有目录和失败的半成品，不直接覆盖；工具材料的恢复与 mediasrv 当次实际运行基线的回退分别核对。这个缺口尚未实现，不因材料完整或历史播放通过而消失。具体必要项与暂缓项由交付报告维护；本次不重打 ZIP，也不改变包内历史说明或其校验记录。
