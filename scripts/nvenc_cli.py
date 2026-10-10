# SPDX-License-Identifier: GPL-3.0-or-later
"""SSH terminal menu. Runtime helpers are imported only on Linux action execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from nvenc_bootstrap import licensed

VERSION='0.1.1'
PROJECT=Path(__file__).absolute().parents[1]
DATA=Path('/vol1/1000/Solis_FnOS_NVENC')
CHOICES={'1':'check','2':'install','3':'update-tool','4':'status','5':'verify',
         '6':'disable','7':'uninstall-patch','8':'uninstall-tool'}
MENU='''
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
'''

def parser():
    p=argparse.ArgumentParser(description='fnOS NVENC SSH 安装与恢复菜单；未知组合停止。')
    p.add_argument('action',nargs='?',default='menu',choices=['menu',*CHOICES.values(),'deploy','rollback','build','boot-prepare','restore-tool'])
    p.add_argument('--bundle',type=Path,help='已通过固定候选身份门的本地 bundle 目录')
    p.add_argument('--workdir',type=Path,help='本轮不存在的构建输出目录')
    p.add_argument('--idle-confirmed',action='store_true',help='调用者已当次确认所有播放和转码均退出')
    p.add_argument('--json',action='store_true',help='只输出结构化结果')
    p.add_argument('--trial-contract',type=Path,help=argparse.SUPPRESS)
    p.add_argument('--audio-confirmed',action='store_true',help='本次 720p/跳转后已人工确认声音正常、无明显不同步')
    return p

def confirm_idle(already,stream=None):
    if already:return
    stream=stream or sys.stdin
    if not stream.isatty():raise RuntimeError('服务变更需要当次空闲确认；包括直接播放。未确认，停止。')
    print('此动作可能重启影视服务。确认所有人退出播放与转码后，输入 IDLE：',flush=True)
    if stream.readline().strip()!='IDLE':raise RuntimeError('未确认空闲，动作取消')

def action_argv(args):
    values=[args.action]
    for name in ('bundle','workdir','trial_contract'):
        value=getattr(args,name,None)
        if value is not None:values.extend(['--'+name.replace('_','-'),value.as_posix()])
    for name in ('idle_confirmed','json','audio_confirmed'):
        if getattr(args,name,False):values.append('--'+name.replace('_','-'))
    return values

def menu(reader=input,writer=print,dispatch=None):
    dispatch=dispatch or (lambda action:execute(parser().parse_args([action])))
    while True:
        writer(MENU)
        try:value=reader('请选择 [0-8]：').strip()
        except (EOFError,KeyboardInterrupt):return 0
        if value=='0':return 0
        action=CHOICES.get(value)
        if not action:writer('请输入 0 到 8。');continue
        try:dispatch(action)
        except (RuntimeError,OSError,ValueError,KeyError,subprocess.SubprocessError) as error:writer('STOP：'+str(error))

def payload_files(project):
    files=['fnos-nvenc.sh','LICENSE','docs/runtime_profile.json','docs/build_sources.json',
           'docs/build_packages.txt','docs/installer_status.json','docs/quick_start.md',
           'patches/COPYING.GPLv3','patches/ac4_decoder.patch','patches/ac4_parser_type.patch',
           'build/prepare_public_environment.sh','build/run_public_build.sh','tests/test_runtime_files.sh','scripts/runtime_files.sh']
    files += ['scripts/'+name for name in ('nvenc_cli.py','nvenc_build.py','nvenc_install.py','nvenc_bootstrap.py',
              'nvenc_autostart.py','nvenc_runtime.py','build_libavcodec.sh','inspect_libavcodec.c')]
    return files

def choose_bundle(args,profile,build_if_missing=False):
    from nvenc_build import digest,build,safe_path
    candidates=[args.bundle] if args.bundle else [PROJECT/'bundle',PROJECT/'artifacts/runtime_bundle']
    recovery=args.action in ('disable','uninstall-patch','rollback','uninstall-tool')
    if not args.bundle and recovery:
        candidates.append(Path('/opt/solis-fnos-nvenc/managed')/profile['candidate_sha256'])
    if not args.bundle:
        from nvenc_install import Installer
        base=Installer()
        if not recovery and base.base.exists() and (base.base/'owner.json').is_file():
            current=base.current();candidates.append(base.base/'releases'/current['release']/'bundle')
    for value in candidates:
        if not value:continue
        folder=safe_path(value);library=safe_path(folder/'libavcodec.so.62')
        if library.is_file():
            if library.stat().st_size!=16516408 or digest(library)!=profile['candidate_sha256']:
                raise RuntimeError('候选库身份不符，保留并停止')
            return folder
    if build_if_missing:
        output=args.workdir or DATA/'builds'/('build-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8])
        return build(PROJECT,output)
    return None

def install_tool(bundle):
    from nvenc_install import Installer,safe,inventory
    source=PROJECT
    # A self-contained staging tree prevents private evidence from entering a release directory.
    staging=safe(DATA/'tmp'/('install-input-'+uuid.uuid4().hex));staging.mkdir(mode=0o700,parents=True)
    files=payload_files(source)
    for name in files:
        path=safe(source/name);target=staging/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with target.open('xb') as output:output.write(path.read_bytes())
        os.chmod(target,0o600)
    for name in ('libavcodec.so.62','identity.json'):
        target=staging/'bundle'/name;target.parent.mkdir(mode=0o700,exist_ok=True)
        with target.open('xb') as output:output.write(safe(bundle/name).read_bytes())
        os.chmod(target,0o600);files.append('bundle/'+name)
    runner=b'#!/bin/bash\nset -euo pipefail\nroot=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)\nexec /usr/bin/python3 -B "$root/bootstrap.py" "$@"\n'
    result=Installer().install(staging,files,VERSION,adopt=True,bootstrap={'runner.sh':runner,'bootstrap.py':(source/'scripts/nvenc_bootstrap.py').read_bytes()})
    result['input_preserved']=str(staging)
    return result

def playback_receipt(controller,audio=False):
    from nvenc_runtime import run,sha,Refused
    service=controller.host.service();boot=controller.host.info()['boot']
    rows=run(['nvidia-smi','pmon','-c','1','-s','um']).splitlines();records=[]
    for row in rows:
        fields=row.split()
        if len(fields)<3 or not fields[0].isdigit() or not fields[1].isdigit():continue
        pid=int(fields[1]);process=Path('/proc',str(pid))
        try:
            before=(process/'stat').read_text().split(') ',1)[1].split();ancestor=pid;bound=False
            for _ in range(64):
                if ancestor==service['pid']:bound=True;break
                if ancestor<=1:break
                ancestor=int(Path('/proc',str(ancestor),'stat').read_text().split(') ',1)[1].split()[1])
            if not bound:continue
            mapped=set()
            for line in (process/'maps').read_text().splitlines():
                words=line.split(None,5)
                if len(words)==6 and Path(words[5]).name=='libavcodec.so.62':mapped.add(words[5])
            if mapped!={controller.library}:raise Refused('GPU 子进程未唯一加载本候选')
            identity=controller.identity(controller.library)
            if identity['sha256']!=controller.p['candidate_sha256']:raise Refused('GPU 库身份不符')
            after=(process/'stat').read_text().split(') ',1)[1].split()
            if before[19]!=after[19]:raise Refused('GPU 子进程身份发生变化')
            records.append({'pid':pid,'start_ticks':before[19],'comm':(process/'comm').read_text().strip(),
                            'codec_path':controller.library,'codec_sha256':identity['sha256'],'parent_bound':True})
        except (FileNotFoundError,ProcessLookupError):continue
    if not records:raise Refused('未找到绑定原生服务的真实 GPU 子进程；请保持 720p 播放后重试')
    if not audio:
        if not sys.stdin.isatty():raise Refused('本次声音与跳转确认尚缺；不复用旧听感')
        print('完成本次原生 720p 和一次跳转，声音正常且无明显不同步后输入 AUDIO_OK：')
        if input().strip()!='AUDIO_OK':raise Refused('本次听感未确认')
    result={'schema':1,'boot':boot,'profile':controller.p['id'],'gpu_consumers':records,
            'human_confirmation':'720p_one_seek_audio_normal_sync','full_parity':'FAIL','long_term':'NOT_VERIFIED'}
    from nvenc_install import atomic_json
    report=Path('/var/lib/solis-fnos-nvenc')/('playback-'+uuid.uuid4().hex+'.json');atomic_json(report,result)
    return {'operation':'BOUNDED_PLAYBACK_RECORDED','report':str(report),'evidence':result}

def execute(args):
    if sys.platform!='linux':raise RuntimeError('真实动作只支持 Linux；Windows 可查看帮助或运行本地测试')
    if os.geteuid()!=0:
        if not sys.stdin.isatty():raise RuntimeError('需要标准 SSH 终端 sudo 提权；请在终端运行此命令')
        os.execvp('sudo',['sudo','--','/usr/bin/python3','-B',str(Path(__file__).absolute()),*action_argv(args)])
    from nvenc_runtime import Controller,Refused
    from nvenc_autostart import AutoController,ManagedHost,AUTO_DROPIN,TRIAL
    from nvenc_install import Installer,atomic_json,assert_no_consumers,safe
    from nvenc_build import build
    profile=json.loads((PROJECT/'docs/runtime_profile.json').read_text())
    acceptance=json.loads((PROJECT/'docs/installer_status.json').read_text());host=ManagedHost()
    if args.action=='build':
        folder=args.workdir or DATA/'builds'/('build-'+uuid.uuid4().hex)
        return {'bundle':str(build(PROJECT,folder))}
    if args.action=='restore-tool':
        probe=AutoController(Path('/'),PROJECT/'bundle',profile,host)
        with probe.lock():
            require_paused(probe)
            return Installer().restore_previous()
    if args.action=='update-tool':
        from nvenc_install import InstallRefused
        installer=Installer()
        if (installer.base/'owner.json').is_file():
            try:installer.current()
            except InstallRefused:
                probe=AutoController(Path('/'),PROJECT/'bundle',profile,host)
                with probe.lock():
                    require_paused(probe);result=installer.restore_previous()
                return {'operation':'TOOL_REPAIRED',**result}
    if args.action in ('disable','uninstall-patch','rollback'):
        recovery_bundle=args.bundle or PROJECT/'bundle'
        if not (recovery_bundle/'libavcodec.so.62').exists():
            recovery_bundle=Path('/opt/solis-fnos-nvenc/managed')/profile['candidate_sha256']
        probe=AutoController(Path('/'),recovery_bundle,profile,host)
        state=probe.state()
        if probe.owned_hook() or (state and state['phase'] in ('restoring','recovery_required')):
            confirm_idle(args.idle_confirmed)
            return probe.disable()
    bundle=None if args.action=='boot-prepare' else choose_bundle(args,profile,build_if_missing=False)
    controller=Controller(Path('/'),bundle or PROJECT/'bundle',profile,host)
    auto=AutoController(Path('/'),bundle or PROJECT/'bundle',profile,host,verified=bool(acceptance['autostart_verified'] and acceptance['nas_installer_verified']))
    if args.action=='boot-prepare':return auto.boot_prepare()
    if args.action=='check':
        required=('bash','python3','git','docker','sudo','systemctl','nvidia-smi','readelf','ldd')
        missing=[name for name in required if not shutil.which(name)]
        info=controller.component_check()
        if info['driver']!=profile['driver']:raise Refused('驱动组合未知')
        if info['api']<profile['candidate_api']:raise Refused('驱动接口不足')
        for path,expected in profile['dependencies'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:raise Refused('外部依赖身份变化：'+path)
        free=shutil.disk_usage(DATA).free
        return {'environment':'PASS' if not missing else 'MISSING_COMMANDS','missing':missing,
                'compatibility':controller.check() if bundle else 'BUILD_REQUIRED','candidate_available':bool(bundle),
                'disk_free_bytes':free,'build_space':'PASS' if free>=8*1024**3 else 'INSUFFICIENT_FOR_BUILD','license':info['license'],
                'installer_verified':acceptance['nas_installer_verified'],'autostart_verified':acceptance['autostart_verified']}
    if args.action=='status':
        installer=Installer();tool=installer.current() if (installer.base/'owner.json').is_file() else None
        return {'tool':tool,'patch':auto.status(),'legacy':controller.status() if bundle else 'NO_BUNDLE'}
    if args.action in ('install','update-tool'):
        controller.component_check()
        if host.info()['driver']!=profile['driver']:raise Refused('驱动组合未知')
        if args.trial_contract:
            path=safe(args.trial_contract);info=path.stat()
            if info.st_uid!=0 or info.st_mode&0o777!=0o600:raise Refused('试用合同必须为 root:600 普通文件')
            atomic_json(Path(TRIAL),json.loads(path.read_text()))
        if args.action=='install':auto.gate(auto.state());confirm_idle(args.idle_confirmed)
        if args.action=='update-tool' and auto.owned_hook():raise Refused('更新工具前先暂停补丁，保留恢复记录')
        bundle=bundle or choose_bundle(args,profile,True)
        controller.bundle=bundle;auto.bundle=bundle;controller.static_check()
        if Path('/run/systemd/system/mediasrv.service.d/95-solis-nvenc-managed.conf').exists():
            raise Refused('旧临时补丁仍启用，请先 rollback 再安装新工具')
        with auto.lock():
            auto.require_closed_transaction()
            result=install_tool(bundle)
        if args.action=='install':
            try:result['patch']=auto.enable()
            except Exception:
                installer=Installer()
                if (installer.base/'previous.json').exists():
                    with auto.lock():
                        require_paused(auto);installer.restore_previous()
                raise
        return result
    if not bundle:raise Refused('候选库材料缺失；先从菜单安装或提供已校验 bundle')
    if args.action in ('disable','uninstall-patch','rollback'):
        confirm_idle(args.idle_confirmed)
        state=auto.state()
        if auto.owned_hook() or (state and state['phase'] in ('restoring','recovery_required')):return auto.disable()
        with auto.lock():return legacy_action(controller,'rollback')
    if args.action=='deploy':
        confirm_idle(args.idle_confirmed)
        if auto.owned_hook():raise Refused('持久补丁已配置，不混用临时 deploy')
        with auto.lock():return legacy_action(controller,'deploy')
    if args.action=='verify':return playback_receipt(auto,args.audio_confirmed)
    if args.action=='uninstall-tool':
        with auto.lock():
            require_paused(auto);host.hook_absent()
            os.chdir('/')
            assert_no_consumers([Path('/opt/solis-fnos-nvenc/managed')])
            return Installer().uninstall(assert_no_consumers)
    raise Refused('未知动作')

def main():
    args=parser().parse_args()
    if args.action=='menu':
        if not sys.stdin.isatty():print('请在 SSH 交互终端运行菜单，或指定动作；用 --help 查看。');return 1
        if sys.platform=='linux' and os.geteuid()!=0:
            os.execvp('sudo',['sudo','--','/usr/bin/python3','-B',str(Path(__file__).absolute()),'menu'])
        return menu(dispatch=lambda action:show(execute(parser().parse_args([action])),False))
    result=execute(args);show(result,args.json);return 0

def legacy_action(controller,action):
    import fcntl
    fd=os.open(controller.path('/run/lock/solis-nvenc.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return getattr(controller,action)()

def require_paused(auto):
    state=auto.state()
    if auto.owned_hook() or Path('/run/systemd/system/mediasrv.service.d/95-solis-nvenc-managed.conf').exists():raise RuntimeError('先暂停或卸载补丁')
    if state and state['phase'] in ('switching','restoring','recovery_required'):raise RuntimeError('恢复事务未关闭，先完成恢复')

def show(result,structured=False):
    if structured:
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    operation=result.get('operation')
    messages={'INSTALLED':'工具安装完成，上一版与恢复材料保留。','ALREADY_INSTALLED':'同一版本已安装，无需覆盖。',
              'AUTO_ENABLED':'补丁已接入，影视服务已重启；每次启动将重新检查。',
              'ALREADY_LOADED':'同一补丁已加载，无需再次重启。','RESTORED':'已核对并恢复当次开机基线。',
              'ALREADY_INACTIVE':'当前没有本工具覆盖，无需切换。','TOOL_UNINSTALLED':'工具卸载完成；恢复记录与历史材料保留。',
              'BOUNDED_PLAYBACK_RECORDED':'本次有限播放与实际 GPU 映射记录已保存。'}
    messages['CONFIG_DISABLED_NOT_RESTORED']='已撤销本工具启动注入；当前组件或开机变化，未重启，恢复结果尚未验证。请保留证据并联系维护者。'
    messages['TOOL_REPAIRED']='损坏版本已保留，工具指针已恢复到经核验的上一版。'
    messages['SWITCHED_EXISTING']='已验证并切换到保留版本，文件没有覆盖。'
    if operation:print(messages.get(operation,operation))
    if 'environment' in result:
        print('环境：'+result['environment'])
        if result.get('missing'):print('缺少命令：'+', '.join(result['missing']))
        print('候选库：'+('已校验' if result['candidate_available'] else '首次安装时隔离构建'))
        print('开机流程现场验证：'+('已通过' if result['autostart_verified'] else '尚未通过，启用门关闭'))
    patch=result.get('patch')
    if result.get('tool'):print('工具版本：'+result['tool']['release'])
    if isinstance(patch,dict):
        if 'operation' in patch:show(patch)
        else:
            print('自动启用：'+('已设置' if patch['enabled'] else '未设置'))
            print('实际候选加载：'+('已加载' if patch['loaded'] else '未加载'))
            print('启动检查：'+patch['startup'])
    for name,label in (('release','工具版本'),('bundle','构建材料'),('report','证据记录'),('input_preserved','本轮安装输入')):
        if name in result:print(label+'：'+str(result[name]))
    print('完整原版功能对等仍未通过；其他格式与长期稳定性未验证。')

if __name__=='__main__':
    try:sys.exit(main())
    except (RuntimeError,OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        print('STOP：'+str(error),file=sys.stderr);sys.exit(1)
