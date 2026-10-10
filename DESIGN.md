# Solis_FnOS_NVENC 设计入口

状态：SSH 安装器的固定公开来源双构建匹配既有候选；安装、更换、一次整机重启、开机实际加载、有限原生播放、卸载和新 boot 恢复已通过。现场最终恢复原可用版本。发布状态与证据见[安装器报告](docs/installer_report.md)，项目意图见 [Blueprint](docs/blueprint.md)。

## 职责与边界

本工程维护应用层兼容补丁、构建、校验和回退材料；Solis_Pvescript 保持其 PVE/vGPU/Guest 驱动与 Toolkit 职责。官方影视组件、宿主运行环境和 NVIDIA License 不归本工程改写。

旧试验采取独立候选 libavcodec 与 mediasrv 的 `/run` 临时覆盖，具体指针及证据限制由 [来源与边界](docs/source_and_evidence.md)维护。正式代码保留单库交付与单服务回退边界；本地构建/CPU 回归及有限现场证据由相应报告维护。源码、构建制品、运行接入和持久启用分别关闭，不互相替代。

`patches/` 保存两份固定补丁及 GPLv3 文本；`scripts/` 保存构建核心、材料/WAV 校验与回退支持；`tests/` 保存小型本地验证；`docs/` 保存维护条件、材料身份和精简历史事实。源码和脱敏共享文档加入 Git，源码包与候选库留在忽略的 `artifacts/`。不收纳旧证据整包、试验视频、截图、失败候选或一次性 SSH 启动器。目录只按实际内容创建。

新 demux 补丁另存，不改变两份固定补丁。实验 libavformat 与最小配套库仅用于本地 AC4 消费链路；公开入口只构建固定单库。原 Controller 保留历史临时接入接口。

## SSH 安装器结构

`fnos-nvenc.sh` → `nvenc_cli.py` 提供终端菜单和标准 sudo；`nvenc_build.py` 只消费固定公开下载和仓库源码，在固定 Docker 环境双构建并要求匹配候选。`nvenc_install.py` 管理版本目录、SHA256 清单和普通 JSON 原子指针；稳定 bootstrap 在执行版本代码前验证整份清单，损坏文件保留。

`nvenc_autostart.py` 管理独立 `/etc` 96 drop-in 与 `/run` 环境文件。启动时先清空注入，再验证组件和本 boot 恢复材料，恢复点持久保存成功才写环境。启动准备与实际映射分开记录。重启前释放锁，外层事务保持 switching；其他操作不能介入。未知组件或旧 boot 只允许撤销自有配置，不重放旧恢复点。

运行位置 `/opt/solis-fnos-nvenc/tool/releases/<version-fingerprint>`，源码和构建数据 `/vol1/1000/Solis_FnOS_NVENC`，恢复记录 `/var/lib/solis-fnos-nvenc`。不使用符号链接；工具卸载先验证清单和消费者，只回收自身新建且身份一致的库，保留历史库、备份、源码和恢复材料。

## 必要文档导航

| 文档 | 用途 | 受众 | 状态 |
| --- | --- | --- | --- |
| [Blueprint](docs/blueprint.md) | explanation：唯一项目意图 | 用户、负责人 | current |
| [安装器实施](docs/ssh_installer_plan.md) | plan：三个获批里程碑与接口 | 负责人 | in progress |
| [安装器报告](docs/installer_report.md) | evidence：公开双构建、隔离、现场与发布分层 | 用户、负责人 | in progress |
| [README](README.md) | reference：用户入口与限制 | 用户 | current |
| [项目规则](AGENTS.md) | reference：持久绑定与执行边界 | 负责人 | current |
| [来源与边界](docs/source_and_evidence.md) | reference：授权、来源映射、历史结论与清理状态 | 负责人 | current |
| [维护说明](docs/maintenance.md) | how-to/reference：本地验证、构建条件、许可与回退限制 | 负责人 | current |
| [简单使用说明](docs/quick_start.md) | how-to：短命令、升级、状态与回退 | 用户 | 已验证组合入口开放 |
| [交付补齐报告](docs/delivery_report.md) | evidence：新私人包、校验修正、安装材料及本项目标准例外 | 用户、负责人 | 本地材料；现场首装未验证 |
| [历史单库工具报告](docs/nas_tool_report.md) | evidence/runtime：上一包版本/依赖、部署/恢复及播放阻断 | 用户、负责人 | historical，原记录保留 |
| [合并完成报告](docs/completion_report.md) | evidence/runtime：消费者修正、精确旧材料收尾、新单库播放及条件交付 | 用户、负责人 | 本有限包已完成 |
| [本地交付报告](docs/local_delivery_report.md) | evidence/design：AC4 上游修复、部署模拟及重启恢复边界 | 负责人 | 本轮本地证据 |
| [运行身份](docs/runtime_profile.json) | reference：单库适用组合及 NAS 播放门 | 工具、负责人 | 已知组合有限验证通过 |
| [材料清单](docs/materials.json) | reference：固定材料身份与整理代码来源 | 负责人、校验器 | current |
| [历史检查记录](docs/historical_checks.json) | evidence：脱敏历史短测与单片观察 | 负责人 | historical |
| [构建报告](docs/build_report.md) | evidence：冻结输入、两次干净构建、制品比较及限制 | 负责人 | 本轮本地证据 |
| [功能报告](docs/functional_report.md) | evidence：保存库的 CPU 合成回归、身份、警告与待核对现象 | 负责人 | 本轮本地证据 |
| [准备报告](docs/preparation_report.md) | evidence：AC4、独立音频复核、完整维护入口及现场缺口 | 用户、负责人 | 当前本地证据 |
| [飞牛临时实测方案](docs/nas_trial_plan.md) | plan：已批准的单服务临时测试/恢复边界与后续停止门 | 用户、负责人 | 已执行收尾，后续另批 |
| [飞牛现场报告](docs/nas_trial_report.md) | evidence/runtime：独立 GPU、AC4 集成失败、接入失败与恢复/保护/收尾 | 用户、负责人 | 当前有限现场证据 |
| [后续有限包报告](docs/nas_followup_report.md) | evidence/runtime：AC4 包边界定位、容器只读核查、正确路径原生复测及恢复 | 用户、负责人 | 已收尾；原生有限项/恢复通过 |
| [清理回执](docs/cleanup_receipt.json) | evidence：精确目标、大小、回收与恢复状态 | 负责人 | 本轮清理记录 |

TODO.md 和 DEVLOG.md 是忽略的本地记录，不是共享权威。不创建重复 docs 总目录。

## 未决与更新触发

固定单库、新 demux 实验、工具模拟及真实 NAS 是不同层。上游 raw AC4 本地默认链路已修复；厂商默认消费者/完整源码及恢复官方组件仍未闭合；工具本轮单路原生有限项已通过。工具恢复的是当次历史可用库，完整原版功能对等仍 FAIL，其他格式和长期稳定性仍未验证。详见维护说明和对应报告，不从部署/恢复通过扩大原生结论。

架构、接口、责任、制品或运行边界变化时更新；里程碑关闭时核对导航、当前结论和未决事项。
