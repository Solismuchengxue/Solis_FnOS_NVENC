# Solis_FnOS_NVENC 项目执行规则

## Swift Cycle

- 本项目已采用 `$swift-cycle`。处理项目任务时必须先加载该 Skill，由 Agent 在后台判断阶段、选择最小文档档位并维护受影响的权威文档。
- 当前规范源：`F:\60_Infrastructure_and_Operations\02_Skills\skill_swift_cycle\skills\swift-cycle\SKILL.md`。若技能未暴露，明确说明并完整读取规范源与本次直接要求的引用，不静默假装已调用安装入口。
- 普通文档同步、必要表格、TODO 和 DEVLOG 维护属于已批准任务包内步骤，不要求用户重复选择模式。新的实质授权、目标或架构变化、唯一权威无法判断或证据否定计划时，才请求决定。
- adoption 不授权发布、部署、秘密操作、删除、生产切换或目录迁移。

## 权威和责任

- `docs/blueprint.md` 是项目意图、结果、范围和非目标的唯一权威；README 是用户入口，DESIGN 是设计和必要文档导航。不得复制第二份项目意图基线。
- 本项目由用户指定的一位项目负责人 L1 维护；本文件不推导组织验收状态。
- 根级 TODO.md 与 DEVLOG.md 为 Git 忽略的本地行动和维护记录。使用前核对存在、跟踪和忽略状态；只有存在且被忽略时按本地记录使用。长期事实进入共享来源。
- 旧试验来源与证据限制见 [来源与边界](docs/source_and_evidence.md)。来源报告不是本项目重新进行的 FNOS 现场验收。

## 环境和安全

- Windows Shell 固定使用 `C:\Program Files\PowerShell\7\pwsh.exe`。涉及 PowerShell、Bash、SSH、跨 Shell 参数或复杂引号时加载 `$powershell-bash-safety`；复杂逻辑保存脚本后以 `-File` 执行。
- 使用 Python、Node.js、包管理器或项目环境前，读取 `C:\Users\smile\.codex\environment.md`；项目声明的版本和锁文件优先。
- SSH 配置只以 `C:\Users\smile\.ssh\config` 为来源；不得猜测目标、地址、用户或密钥。
- 不保存密码、Token、私钥、原始敏感日志或私人影片。不分发 NVIDIA 受限驱动。
- 不修改 Solis_Pvescript 的 public/private 仓库，不接管 PVE/VM、驱动、Toolkit 或 License。
- 当次动作范围以人的直接授权为准。已完成工作包的批准不能用于后续接入、重试、重建、清理或长期启用；必要来源与证据边界集中保存在 [来源与边界](docs/source_and_evidence.md)，现行说明由 DESIGN 导航。
- SSH 菜单公开首版的本地、有限 NAS 和源码 v0.1.0 三里程碑已完成，见[安装器报告](docs/installer_report.md)。该当次发布授权不推广为任意后续发布或运行授权。
- 未获当次明确授权时，不 commit、push、设置 remote、创建仓库或 Codex 任务；不安装、SSH FNOS、重启服务/NAS、下载或重建候选、持久启用或修改运行配置。取消或失败不自动重开密码窗口。
- NAS 现场变更前重新确认所有播放与转码均退出，并核对当次恢复点。旧 boot 合同不能重放；试用授权、检查、实际加载、人工播放确认及恢复分别记录。
- 本项目原生运行、/opt、/var/lib 和相关临时路径例外由 [维护说明](docs/maintenance.md)登记，不改变组织标准或其他项目职责。公开源码与生成材料根为 `/vol1/1000/Solis_FnOS_NVENC/`；现有目录必须保留可恢复材料，不按新目录首装命令覆盖或自动迁移。
- 原样收纳材料核对源/目标 SHA256；整理后的代码保存来源映射并验证，不宣称哈希相同。维护与验证入口不得依赖旧 Codex 工件目录；历史路径只用于追溯。
- 清理必须在正式内容和必要证据验证之后进行。只回收已明确授权、无未解决消费者且无越界 ReparsePoint 的目标；使用 Windows 回收站保留恢复性，失败时保留并报告，不永久删除、不清空回收站、不清理远端。

## 文档与验证

- 普通内容使用简体中文，技术标识保持原文。新 docs 文件使用小写 snake_case；不机械生成完整模板树。
- 每次变更审查最终 diff，运行最近且相称的验证及 `git diff --check`；初始无 HEAD 时也检查 `git diff --cached --check`。
- 文档变更核对受影响 Markdown 链接、非空内容、唯一权威和本地记录忽略状态，未跟踪文件也要覆盖。
- parser、静态检查、构建、制品、运行与消费者是独立证据层；未验证层保持 `UNKNOWN` 或 `NOT_VERIFIED`。不得把部长实施的初始化直接标为独立验收 `ACCEPTED`。
