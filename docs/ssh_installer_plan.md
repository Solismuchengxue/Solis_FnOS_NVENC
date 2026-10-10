# SSH 安装器实施记录

用户已批准公开从零安装、开机自动检查、有限 NAS 整机重启验收及通过后公开 `v0.1.0`。本记录落实批准方案；项目意图仍只由 [Blueprint](blueprint.md)维护。

## 固定约束

- 首版只支持 runtime_profile 的已知组合；固定候选 SHA256 不改变。
- 无私人缓存、历史候选或旧工件依赖；不发布 nonfree 制品、镜像、秘密或影片。
- 材料根 `/vol1/1000/Solis_FnOS_NVENC`；运行 `/opt/solis-fnos-nvenc`；恢复 `/var/lib/solis-fnos-nvenc`。
- 安装/更新按清单和版本指针管理，保留上一版。卸载不动官方或历史材料。
- 服务启动前检查失败不注入；旧 boot 的恢复记录不重放；切换事务释放锁后等待服务启动。
- NAS 变更前重新确认空闲及恢复材料，最终恢复原可用状态；现场失败不公开首版。

## 接口与实施任务

1. `nvenc_build.py`：固定下载、签名、容器环境准备、双构建及身份门。消费 build_sources/materials/build_packages，返回通过的 bundle 路径。测试下载损坏、缺失版本、无私人材料依赖、双构建不符。
2. `nvenc_install.py`：root 所有权、文件清单、版本目录、原子 current.json 指针及旧工具收纳。测试首装、更新、损坏/越界、失败恢复和消费者阻止卸载。
3. `nvenc_autostart.py`：持久 drop-in、环境文件、每次启动检查、按 boot 恢复及事务锁交接。复用既有 Controller 身份验证，不关闭尚未现场验证的自动启用门。测试漂移、过期 boot、忙碌、启动失败、重复操作及卸载恢复。
4. `nvenc_cli.py`/fnos-nvenc.sh：交互菜单、sudo 终端提权、四动作兼容、安装闭环及有限播放证据。测试无 TTY、取消、错误输入、帮助和命令路由。
5. README/quick_start/DESIGN/maintenance/Blueprint：公开用户入口、架构、许可与准确状态；检查公开链接及敏感/制品边界。
6. 本地干净源码副本双构建、相关测试、独立审查；NAS 维护窗口有限验收；通过后 GitHub 发布与干净 clone 检查。

## 审查重点

已有半安装目录、不同版本 state、未知服务覆盖、启动钩子与重启锁、卸载时仍在映射的库，均必须有拒绝或可恢复行为。

## 文档职责

采用 runtime_integration，复用 Blueprint（意图）、README/quick_start（用户）、DESIGN（导航）、AGENTS（指令）、maintenance（运维）、runtime_profile（身份）、TODO/DEVLOG（忽略记录）。新增本记录（实施）和 installer_report（新事实）即可，不另建意图或文档总目录。

## 里程碑

- [x] 本地实现与隔离验证
- [x] 有限 NAS 验收及原可用状态恢复
- [ ] 公开源码 v0.1.0 与 clone 验证
