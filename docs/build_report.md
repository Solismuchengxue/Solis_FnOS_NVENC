# 2026-10-09 有限隔离构建报告

## 结论与授权

`PASS`：固定环境内两次独立干净构建均完成，制品字节一致。该结论仅覆盖本报告所列输入、参数与本地容器，不能提升为 fnOS 消费者兼容、完整原版功能对等或长期稳定性通过。

来源会话 `[D60]Solis_Pvescript负责人` 的用户消息 `01a120a5-0b96-7343-8355-2816abdef3d8` 直接批准“下一步”；负责人已核对上一条建议是补齐隔离构建环境、两次干净构建并停在本地报告。本轮不访问 NAS，不覆盖历史候选，不安装 Windows/WSL 宿主工具，不改全局网络，不提交或发布。

机器数据和详细脱敏日志位于忽略的 `artifacts/rebuild-20261009/`；[机器结果](../artifacts/rebuild-20261009/build_summary.json)与[嵌入配置比较](../artifacts/rebuild-20261009/configuration_comparison.json)只在具有私人材料的本地副本可读。

## 冻结输入、依赖与许可

FFmpeg 8.1.1、两份 AC-4 补丁、API12.1 头文件及签名材料沿用[材料清单](materials.json)固定身份；本轮结束时十项原样材料 SHA256 均不变。依赖版本唯一来源复用[历史包清单](build_packages.txt)，SHA256 `254308a64ba66d5b0292b62d4eab774ceefdd644c8fae5394dbb77d242593f3b`。不另建重复版本锁。

| 项目 | 实测身份 |
| --- | --- |
| 本地承载 | Ubuntu-24.04 WSL2，x86_64，内核 `6.18.33.2-microsoft-standard-WSL2`；现有本地 Docker 29.7.2 |
| 构建 userspace | Debian 12，固定基础镜像 `debian@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587` |
| 冻结环境镜像 | `sha256:168b5407fe9a839977f328d4e18f7c9e79dd596458a93f36a73de6e0e2b0bebc` |
| 私人环境缓存 | `artifacts/rebuild-20261009/environment_image.tar.gz`，467,537,720 字节；SHA256 `ce58a94b008aeb096bb8218b2227627457b231c9067c80d3286eae5dbd396c15` |
| 编译器 / glibc | GCC `12.2.0-14+deb12u1` / `2.36-9+deb12u14` |
| 依赖闭合 | 实际安装 286 项，按包名/版本集合与历史清单精确一致，无增减/升级 |

来源为固定镜像内的 Debian 官方 `bookworm`、`bookworm-updates`、`bookworm-security`，组件 `main non-free`。APT 保留签名检查，对索引错误失败；版本缺失直接阻断，不自动改目标。准备阶段通过现有 WSL 网络完成，未更改 DNS、代理或路由。`environment/` 保存三个签名 InRelease、索引 SHA256、199 个本次下载 deb 的 SHA256、包来源元数据、实际版本和 263 个普通 copyright 文件哈希；完整索引、deb 缓存、版权文本与符号链接随私人环境镜像保存。基础包身份由基础镜像 digest 固定。

实际抽查 FDK AAC、x264、x265、libvpx 与 SVT-AV1 版权文本；FDK AAC 有自身 Fraunhofer 条款，其他包含各自 GPL/LGPL/BSD 等声明，不统一改写项目许可。两个新库的 configure 均声明 `nonfree and unredistributable`，新库、冻结环境和缓存只作私人维护，不能作为可公开再分发发行物。没有下载或分发 NVIDIA 驱动。

缓存已在现有引擎通过 `docker load` 读取，回读镜像 ID 不变；这不是另一个全空 Docker 宿主的恢复验收。

## 两次干净构建与检查

两个新容器从同一冻结镜像启动，均 `--pull never --network none`，无 GPU/端口/宿主 Docker socket挂载；只读输入，独立输出。CPU 2、内存 4 GiB、pids 256，移除 capabilities，启用 no-new-privileges。容器内编译路径固定 `/build/output`，`LC_ALL=C`、`TZ=UTC`、`SOURCE_DATE_EPOCH=0`；未重用源码树、对象文件或编译缓存。

| 本地运行 | 容器 ID 前缀 | UTC 时间 | 结果 |
| --- | --- | --- | --- |
| run1 | `77509ce6dcb4` | 13:03:52–13:06:46 | 构建与局部检查 PASS |
| run2 | `ac55b4e70f3a` | 13:06:50–13:09:42 | 构建与局部检查 PASS |

两个库均为 16,516,408 字节，SHA256 均为 `88e48674062ee5ef71864a2619324772bc856fec78c0d4793920fa7d4c15cd57`，分别保留在 `run1/libavcodec.so.62` 和 `run2/libavcodec.so.62`。编译核心、检查器源文件的三项输入哈希也一致。两个配置均通过 AC-4 parser/decoder 双注册门和 NVENC API12.1 头文件门。

在固定 Debian 容器中以 readelf、nm 和小型 `dlopen` 检查器核对新库与历史候选。检查器只枚举注册及 descriptor，不初始化 GPU、不处理媒体；读取历史候选时使用本次构建的 libavutil/libswresample 辅助库，这不是 fnOS 官方依赖环境。

| 检查 | 两次新库与历史候选比较 |
| --- | --- |
| SONAME /版本 | `libavcodec.so.62` / `62.28.101`，一致 |
| ELF / GLIBC | x86_64；最高 GLIBC 要求 `2.35`，一致 |
| DT_NEEDED | 依赖名称集合一致 |
| 定义导出项 | 179 项，新增 0、缺失 0 |
| codec 注册 | encoder 210、decoder 547，名称/ID 集合新增 0、缺失 0 |
| descriptor | 540 项，名称/ID 集合新增 0、缺失 0 |

新库与历史候选的 SHA256 不同。嵌入 configure 参数除 prefix 外顺序和内容一致：历史 `/work/prefix`，本轮 `/build/output/prefix`。该差异足以阻止声明历史候选字节复现；未做全二进制差异归因，不把哈希差异解释为兼容通过或失败。

7 个 Shell 文件在 Debian Bash 5.2.15 解析通过；ShellCheck 不在冻结环境，`NOT_RUN`。检查器在 GCC `-Wall -Wextra -Werror` 下编译通过。每个构建容器内文件保护测试均 4/4，包含真实符号链接拒绝；未执行服务回退。入口复用已有输出、在裸 WSL 安装依赖时均被拒绝，既有制品哈希不变。

每次 FFmpeg 编译均有 33 条警告，包括 AAC/WMA 的 `-Wstringop-overflow`、VLC 的 `-Warray-bounds`、VVC/FFV1 栈大小以及 AC-4 未用变量等；configure 的 `--fatal-warnings` 不等于编译器全局 `-Werror`。完整日志随各 run 保留，本包未修改固定上游/补丁来处理这些警告，也未调查其运行影响。编译成功不表示警告已关闭。

## 保留、清理与未关闭门

保留私人冻结环境及两次成功制品/日志；失败解包仅保留小型诊断记录，不保留失败候选或源码树。临时构建/检查容器自动移除，环境准备容器在核对本轮身份后移除；项目临时脚本及废弃预检输出在白名单核对后清理。现有五项私人材料、旧回收站和其他项目镜像/容器/卷均不属于清理目标。

完整厂商对应源码仍缺失；历史 10 encoder、8 decoder 缺注册项仍未关闭，完整原版功能对等继续 `FAIL`。媒体格式覆盖、真实服务回退、NAS 重启恢复、跨版本及长期稳定性仍 `NOT_VERIFIED`；当前 NAS 状态 `UNKNOWN`。本轮停在本地构建报告，后续运行包须另行决定。
