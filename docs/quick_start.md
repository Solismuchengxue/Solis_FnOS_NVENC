# 快速使用

完整安装、准备条件、菜单和卸载说明见 [README](../README.md)。首版只支持身份合同覆盖的 fnOS 1.2.0701 / GRID P4-4Q / R535 535.309.01；安装与开机门已通过有限现场验收，状态和限制见[安装器报告](installer_report.md)。

在源码目录运行 `bash fnos-nvenc.sh`，密码只在标准 sudo 提示中输入。顺序：检查 → 安装 → 原生 720p / 一次跳转 → 播放验证。服务变更前确认所有人退出播放与转码，包括直接播放。

暂停或卸载先恢复当次开机基线；恢复未验证时保留证据并停止删除。当前版本损坏时从保留的源码目录运行 `sudo bash fnos-nvenc.sh restore-tool`，验证完整上一版后切换普通指针。

历史四命令 `check/deploy/status/rollback` 保留，其中 deploy 仅做临时接入；持久补丁启用时不能混用。安装后的入口为 `sudo bash /opt/solis-fnos-nvenc/tool/runner.sh`。

完整原版功能对等仍 FAIL，其他格式与长期稳定性未验证。源码 GPL-3.0-or-later；nonfree 编译库仅本地私用，不公开分发。
