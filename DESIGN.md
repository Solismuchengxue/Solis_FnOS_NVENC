# Solis_FnOS_NVENC 设计入口

项目意图唯一权威为[项目蓝图](docs/blueprint.md)，用户入口为 [README](README.md)。公开首版的分层验证和发布事实由[安装器报告](docs/installer_report.md)维护；历史工作包不推导新的运行或发布权限。

## 架构与职责

`fnos-nvenc.sh` / `nvenc_cli.py` 提供 SSH 菜单与标准 sudo；`nvenc_build.py` 从固定公开来源编排 Docker 双构建和候选身份门；`nvenc_install.py` 管理版本目录、清单及普通原子指针，bootstrap 执行前核对清单；`nvenc_autostart.py` 管理启动检查、本 boot 恢复点和锁交接，运行控制器保留四命令兼容。

本工程维护应用层单库兼容、检查与恢复。Solis_Pvescript 继续维护 PVE/vGPU/Guest 驱动与 Toolkit；官方组件、宿主和 NVIDIA License 保持原责任边界。现行代码只维护公开单库安装、构建与恢复；AC4 demux、多库及配套媒体实验能力已退役。

## 项目架构图

![Solis fnOS NVENC 项目架构](docs/assets/project_architecture.png)

保留 [Figma 可编辑原图](https://www.figma.com/board/3tIHKaCHRA2wdciTQZij3B)和 [Mermaid 定义](docs/assets/project_architecture.mmd)。图示表达职责与材料流，不表示新增服务。

源码直接克隆到 `/vol1/1000/Solis_FnOS_NVENC/`；`builds/` 和 `tmp/` 为忽略的生成目录，所需临时目录由工具创建。下载在宿主校验，依赖准备与编译在 Docker 内；安装、恢复记录和临时启动状态分别位于 `/opt`、`/var/lib`、`/run`。

版本目录由 root 管理，以普通 JSON 原子指针切换，不使用符号链接。启动前检查失败清空本工具注入；旧 boot 状态不重放。卸载先核对恢复、文件身份及消费者，只移除自身新建且身份匹配的材料。

## 当前文档入口

| 文档 | 用途 | 受众 | 状态 |
| --- | --- | --- | --- |
| [用户手册](README.md) | 安装、使用、更新及卸载 | 用户 | 现行 |
| [项目蓝图](docs/blueprint.md) | 唯一项目意图 | 用户、负责人 | 现行 |
| [项目规则](AGENTS.md) | 执行边界与维护要求 | 负责人 | 现行 |
| [维护说明](docs/maintenance.md) | 公开安装器验证、恢复与材料管理 | 负责人 | 现行 |
| [安装后的快速说明](docs/quick_start.md) | 随工具安装的离线短帮助 | 用户 | 现行 |
| [安装器报告](docs/installer_report.md) | 首版构建、隔离、现场与发布证据 | 用户、负责人 | 现行 |
| [来源与边界](docs/source_and_evidence.md) | 固定来源、必要结论与验证限制 | 负责人 | 现行 |
| [运行身份合同](docs/runtime_profile.json) | 已知组件、依赖和候选身份 | 工具、负责人 | 固定合同 |
| [构建来源](docs/build_sources.json)、[依赖版本](docs/build_packages.txt)、[材料清单](docs/materials.json) | 输入身份与材料追溯 | 工具、负责人 | 固定材料 |
| [发行门状态](docs/installer_status.json) | 首版安装与开机验收门 | 工具、负责人 | 已有有限证据 |

身份合同引用的[合并完成报告](docs/completion_report.md)原路径保留，正文按其原单库工作包理解；只修复链接和状态提示，不改证据正文或合同。旧过程报告与计划不再保存在项目中。TODO.md 和 DEVLOG.md 为 Git 忽略的本地记录。

## 验证限制与更新触发

完整原版功能对等仍 FAIL，其他格式与长期稳定性未验证。源码构建、工具模拟和 NAS 运行是不同证据层；实际映射不代替本次影片的人工播放确认。

架构、接口、交付边界或文档职责变化时更新本入口；当前验证事实进入对应报告，项目意图变化才修改项目蓝图。
