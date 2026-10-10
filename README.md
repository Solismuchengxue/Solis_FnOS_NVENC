# Solis fnOS NVENC

让特定 P4 / R535 环境继续使用飞牛原生影视的 NVENC 转码。通过 SSH 编号菜单完成检查、源码构建、补丁安装、开机检查、暂停和卸载，保留每次开机的恢复记录。

当前版本为 [v0.1.1 源码维护版](https://github.com/Solismuchengxue/Solis_FnOS_NVENC/releases/tag/v0.1.1)：统一中文说明和直接克隆入口，加入项目架构图，退役旧实验与传输文件。固定构建输入、候选库和运行身份合同不变，本版没有新增 NAS 验收。

**首版范围有限：完整原版功能对等仍未通过；其他格式和长期稳定性未验证。** [v0.1.0](https://github.com/Solismuchengxue/Solis_FnOS_NVENC/releases/tag/v0.1.0) 已完成有限 NAS 安装、整机重启、开机检查、普通影片单路 720p、一次跳转及卸载恢复验收，见[安装器报告](docs/installer_report.md)。

## 适用范围

| 项目 | 首版要求 |
| --- | --- |
| fnOS | 1.2.0701，Debian 12 / x86_64 / glibc 2.36 |
| GPU | GRID P4-4Q |
| NVIDIA 驱动 | R535，535.309.01，NVENC API 12.1 |
| 原生影视与依赖 | [身份合同](docs/runtime_profile.json)中 13 项保护文件与 50 项外部库一致 |

同型号也不保证兼容；检查以文件和版本身份为准。未知版本停止安装，系统或影视升级后也不会强行注入旧库。本工程不安装 NVIDIA 驱动、Toolkit 或 License。

## 准备条件

NAS 已具备正常驱动与许可、Git、Bash、Python **3.11 或以上**、Docker、sudo、systemd、readelf、ldd 和 nvidia-smi。构建仅在当前 NAS 的 Docker 容器中进行，不能使用远程 Docker。建议至少 8 GiB 可用构建空间；构建资源上限为 2 CPU / 4 GiB 内存。首次构建需要访问 FFmpeg、GitHub、Docker Hub 和 Debian snapshot。

安装或暂停可能重启影视服务。先让所有人退出播放与转码，包括直接播放；在提示中输入 `IDLE`。密码只在 SSH 终端的标准 `sudo` 提示中输入。

## 克隆并运行

直接在 `/vol1/1000/` 下克隆，仓库根目录就是安装入口，不需要再建 `source` 子目录。以下命令只在前一步成功时继续。

```bash
cd /vol1/1000/ &&
git clone https://github.com/Solismuchengxue/Solis_FnOS_NVENC.git &&
cd /vol1/1000/Solis_FnOS_NVENC/ &&
bash fnos-nvenc.sh
```

已有非空 `Solis_FnOS_NVENC` 目录时，Git 会停止克隆。保留原目录及恢复材料；如果原来克隆在 `source/`，继续从原源码入口使用，不要覆盖或自动搬迁。下面的更新路径适用于新的直接克隆布局。

菜单只在交互终端运行：

```text
Solis fnOS NVENC  |  v0.1.1
  1. 检查环境与兼容性
  2. 安装补丁（构建、安装、开机检查）
  3. 更新／修复工具
  4. 查看状态
  5. 播放验证
  6. 暂停补丁／恢复
  7. 卸载补丁
  8. 卸载工具
  0. 退出
```

## 安装与使用

先选 **1** 检查环境，再选 **2** 安装。首次安装从公开来源下载固定源码、验证签名和 SHA256，在 Docker 内独立构建两次。两个结果都必须匹配已验证候选；不匹配就停止，不修改身份合同放行。随后核对当前恢复点，安装版本目录和单库，设置启动检查，重启影视服务并核对实际加载。

首次安装较慢。项目根下的 `builds/` 保存构建材料，`tmp/` 保存当次暂存；两者被 Git 忽略，不覆盖已有目录，必要证据保全前不清理。再次安装相同版本是幂等操作。已有未知工具、改动过的文件或未完成事务时会停止并保留材料。

维护者本地的 `artifacts/` 是被 Git 忽略的材料目录，公开克隆不包含；公开安装流程自行构建，不需要预先具备这个目录。只保留仍需使用的库、构建输入和恢复材料，不保存已完成试验的日志、输出或重复包。

仍通过原来的飞牛影视入口播放，不增加网址、账户或端口。选择原生 **720p**，完成一次跳转并继续播放；保持播放时在菜单选 **5**，核对声音与音画同步后输入 `AUDIO_OK`。工具保存绑定原生服务的真实 GPU 子进程和实际库映射。状态页的“已加载”不代表所有影片已经验证。

## 开机自动检查

安装补丁时设置本工具独立的持久 systemd drop-in。每次影视服务启动前重新核对组件、驱动和依赖；检查不需要网络或 Docker。失败时清空本工具的注入环境，让原来的服务链启动，并记录原因；其他配置保留。启动准备和实际加载分开显示。

每次开机重新建立恢复点，不能重放上次开机的状态。暂停后自动注入关闭；再次选择安装才启用。首版安装与开机门已按有限现场证据开放，不要编辑验证标记或身份合同绕过检查。

## 更新、修复与暂停

在源码目录取得经核查的新版本后运行菜单，先选 **6** 暂停，再选 **3** 更新工具。新版按清单验证后原子切换普通 JSON 指针，保留上一版，不覆盖旧目录；安装失败保留半成品和旧可用版本。

```bash
cd /vol1/1000/Solis_FnOS_NVENC/ || exit 1
git pull --ff-only
bash fnos-nvenc.sh
```

更新工具不会自动重新启用补丁；检查后选 **2**。当前版本损坏但上一版完整时，从保留的源码入口运行 `sudo bash fnos-nvenc.sh restore-tool`，只恢复工具指针，损坏文件保留。

**6** 暂停补丁并恢复本次开机基线，保留工具和材料。若组件或 boot 已变化，只撤销身份明确的本工具启动配置，提示恢复未验证；不会重放旧合同，也不会自动重启未知环境。保留提示和恢复记录，交给维护者核对。

## 卸载

先退出所有播放，选 **7** 卸载补丁，核对恢复；再选 **8** 卸载工具。工具卸载只移除清单内身份匹配且没有消费者的安装文件。修改过的文件、未知材料、符号链接或仍被映射的库都会阻止删除。

恢复记录、源码目录、历史库和旧工具备份保留。卸载不删除官方影视、驱动或既有历史材料。卸载后仍可在源码目录重新运行安装器。

## 命令行兼容

```bash
sudo bash fnos-nvenc.sh check
sudo bash fnos-nvenc.sh status
sudo bash fnos-nvenc.sh deploy    # 历史临时接入，不设置开机检查
sudo bash fnos-nvenc.sh rollback  # 恢复当次基线
```

新动作还包括 `install`、`update-tool`、`verify`、`disable`、`uninstall-patch`、`uninstall-tool` 和 `build`。`--help` 查看参数，`--json` 用于结构化读回。已启用持久补丁时不能混用临时 `deploy`。安装后的稳定入口为 `sudo bash /opt/solis-fnos-nvenc/tool/runner.sh`；[离线短说明](docs/quick_start.md)随工具安装。

## 常见问题

- **出现 STOP？** 保存短提示，停止重复覆盖或反复重启；不要修改 SHA、验证标记或官方文件。
- **构建不一致？** 保留两次输出。即使两个结果互相一致，只要不匹配固定候选，也不会接入。
- **升级后没有注入？** 启动检查已拒绝未知组件；保留原服务链，等待新适用合同。
- **听感确认为什么每次都要做？** 历史声音确认不能代替这次影片、跳转和实际候选的结果。
- **日志与空间？** 终端显示动作结果；启动消息由 systemd 接收。恢复记录、构建和旧版本不会自动清理；定期由维护者核对自身材料。`journalctl -u mediasrv.service -n 100 --no-pager` 仅查看近期服务消息，避免公开私人原始日志。

## 来源、许可与维护

自有代码采用 [GPL-3.0-or-later](LICENSE)。第三方补丁保留其原声明及[来源记录](docs/source_and_evidence.md)；[固定公开构建输入](docs/build_sources.json)可核查。构建使用 `nonfree` 选项，产物不可再分发；仓库和 Release 只发布源码与说明，**不发布编译库、驱动或构建镜像**。参见 [FFmpeg 许可说明](https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.1.1/LICENSE.md)。

菜单交互参考 [KIAUH](https://github.com/dw-0/kiauh)，实现由本工程维护。开发、[Figma 架构图](DESIGN.md#项目架构图)和证据导航见 [DESIGN](DESIGN.md)及[维护说明](docs/maintenance.md)。完整原版功能对等仍 **FAIL**；本项目不是厂商官方兼容承诺。
