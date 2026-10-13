# SPDX-License-Identifier: GPL-3.0-or-later
"""One owned startup hook; immutable component gates and per-boot recovery."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shlex
import stat
import time
import uuid
from nvenc_runtime import Controller, Refused, LinuxHost, run, sha
from nvenc_install import atomic_json, atomic_bytes, safe, InstallRefused, Installer

AUTO_DROPIN='/etc/systemd/system/mediasrv.service.d/96-solis-nvenc-autostart.conf'
ENV_FILE='/run/solis-fnos-nvenc/mediasrv.env'
AUTO_STATE='/var/lib/solis-fnos-nvenc/autostart.json'
TRIAL='/var/lib/solis-fnos-nvenc/installer_trial.json'
LOCK='/run/lock/solis-nvenc-installer.lock'
HOOK=("[Service]\nExecStartPre=+/usr/bin/env -u LD_LIBRARY_PATH /bin/bash /opt/solis-fnos-nvenc/tool/runner.sh boot-prepare\n"
      "EnvironmentFile=-/run/solis-fnos-nvenc/mediasrv.env\n").encode()

class ManagedHost(LinuxHost):
    def info(self):
        from nvenc_bootstrap import licensed
        value=super().info()
        if not licensed(run(['nvidia-smi','-q'])):raise Refused('驱动许可尚未确认为 Licensed，停止注入')
        value['license']='Licensed'
        return value
    def reload(self):run(['systemctl','daemon-reload'])

    def hook_absent(self):
        if AUTO_DROPIN in self.service()['dropins']:raise Refused('启动覆盖仍在有效配置中')
        value=run(['systemctl','show','mediasrv','-p','ExecStartPre'])
        if '/opt/solis-fnos-nvenc/tool/runner.sh' in value:raise Refused('本工具启动命令仍在有效配置中')

    def service(self):
        value=super().service()
        if value['pid']:
            with Path('/proc',str(value['pid']),'environ').open('rb') as stream:data=stream.read(1048577)
            if len(data)>1048576:raise Refused('服务环境超过读取上限')
            paths=[s.decode() for s in data.split(b'\0') if s.startswith(b'LD_LIBRARY_PATH=')]
            if len(paths)>1:raise Refused('实际服务环境库路径不唯一')
            value['environment']=paths[0] if paths else ''
        return value

class AutoController(Controller):
    def __init__(self,root,bundle,profile,host,verified=False):
        super().__init__(root,bundle,profile,host);self.verified=verified
        self.uid=Path(root).stat().st_uid

    @contextmanager
    def lock(self):
        path=self.path(LOCK);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:
            info=os.fstat(stream.fileno())
            if info.st_uid!=self.uid or stat.S_IMODE(info.st_mode)&0o077:raise Refused('事务锁权限不符')
            try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as error:raise Refused('另一安装动作正在执行') from error
            yield

    def state(self):
        path=self.path(AUTO_STATE)
        if not path.exists():return None
        identity=self.identity(AUTO_STATE)
        if identity['uid']!=self.uid or identity['mode']!=0o600:raise Refused('自动启用记录权限不符')
        state=json.loads(path.read_text())
        if state.get('schema')!=1 or state.get('profile')!=self.p['id']:raise Refused('自动启用记录身份不符')
        return state

    def save_auto(self,state):atomic_json(self.path(AUTO_STATE),state)

    def owner(self):
        pid=os.getpid();ticks=Path('/proc',str(pid),'stat').read_text().split(') ',1)[1].split()[19]
        return {'pid':pid,'ticks':ticks,'boot':self.host.info()['boot']}

    def owner_alive(self,state):
        owner=state.get('owner',{})
        if owner.get('boot')!=self.host.info()['boot']:return False
        try:return Path('/proc',str(int(owner['pid'])),'stat').read_text().split(') ',1)[1].split()[19]==owner['ticks']
        except (FileNotFoundError,ProcessLookupError,KeyError,ValueError):return False

    def reload_without_hook(self):
        self.host.reload()
        if AUTO_DROPIN in self.host.service()['dropins']:raise Refused('撤销覆盖后读回不符')
        if hasattr(self.host,'hook_absent'):self.host.hook_absent()

    def archive(self,state):
        if not state:return
        data=json.dumps(state,sort_keys=True).encode();target=self.path(AUTO_STATE).parent/('autostart-history-'+sha(data)+'.json')
        if not target.exists():atomic_json(target,state)

    def owned_hook(self):
        path=self.path(AUTO_DROPIN)
        if not path.exists():return False
        identity=self.identity(AUTO_DROPIN)
        if path.read_bytes()!=HOOK or identity['uid']!=self.uid or identity['mode']!=0o644:
            raise Refused('同名启动覆盖不属于本工具，保留并停止')
        return True

    def trial_valid(self,state=None):
        path=self.path(TRIAL)
        if not path.exists():return False
        identity=self.identity(TRIAL)
        if identity['uid']!=self.uid or identity['mode']!=0o600:raise Refused('有限试用合同权限不符')
        trial=json.loads(path.read_text());now=time.time()
        machine=self.path('/etc/machine-id')
        if not machine.is_file():return False
        if trial.get('schema')!=1 or trial.get('authorization')!='user-approved-ssh-installer-v0.1.0':return False
        if trial.get('profile_sha256')!=sha(json.dumps(self.p,sort_keys=True).encode()):return False
        if trial.get('machine_sha256')!=sha(machine.read_bytes()):return False
        if not now<trial.get('expires_at',0)<=now+86400:return False
        boot=self.host.info()['boot'];seen=(state or {}).get('trial_boots',[])
        return boot==trial.get('initial_boot') or (trial.get('allow_one_reboot') is True and len(set(seen+[boot]))<=2 and trial.get('initial_boot') in seen)

    def gate(self,state=None):
        if self.verified and self.p.get('nas_tool_verified') is True:return
        if not self.trial_valid(state):raise Refused('当前运行合同或安装与开机流程尚未现场验收；只允许本轮有界试用合同')

    def clear_environment(self):
        path=self.path(ENV_FILE)
        if path.exists():
            identity=self.identity(ENV_FILE)
            if identity['uid']!=self.uid or identity['mode']!=0o600:raise Refused('注入环境文件权限未知，保留并停止')
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        atomic_bytes(path,b'')

    def inject_environment(self):
        value=str(Path(self.library).parent)+':'+self.p['official_dir']+':/usr/trim/lib'
        self.write(ENV_FILE,('LD_LIBRARY_PATH='+value+'\n').encode())

    def verify_recovery(self,baseline):
        info,_=self.static_check()
        if info['boot']!=baseline['boot']:raise Refused('当前恢复记录属于另一开机，拒绝重放')
        for path,identity in {**baseline['protected'],**baseline['dropins'],baseline['loaded']:baseline['loaded_identity']}.items():
            if self.identity(path)!=identity:raise Refused('恢复材料身份变化：'+path)
        allowed=set(baseline['dropins'])
        if self.owned_hook():allowed.add(AUTO_DROPIN)
        if set(self.host.service()['dropins'])!=allowed:raise Refused('恢复时存在未知服务覆盖')

    def boot_baseline(self):
        info,_=self.static_check();service=self.host.service();dropins={}
        for path in service['dropins']:
            if path==AUTO_DROPIN:self.owned_hook();continue
            expected=self.p['allowed_dropins'].get(path)
            if not expected or self.identity(path)['sha256']!=expected:raise Refused('开机存在未知覆盖')
            dropins[path]=self.identity(path)
        environment=service['environment']
        words=shlex.split(environment)
        if any(not w.startswith('LD_LIBRARY_PATH=') for w in words) or len(words)>1:raise Refused('开机环境库路径不唯一')
        directories=words[0].split('=',1)[1].split(':') if words else []
        directories=list(dict.fromkeys(directories+[self.p['official_dir']]))
        loaded=None
        for directory in directories:
            if not directory.startswith('/'):raise Refused('开机库路径不规范')
            candidate=directory+'/libavcodec.so.62'
            if self.path(candidate).is_file():loaded=candidate;break
        expected=self.p['allowed_baseline'].get(loaded)
        if not expected or self.identity(loaded)['sha256']!=expected:raise Refused('开机原有库身份未知')
        return {'boot':info['boot'],'loaded':loaded,'loaded_identity':self.identity(loaded),'environment':environment,
            'environment_sha256':service.get('environment_sha256'),'dropins':dropins,'proof':'CONFIG_BEFORE_START',
            'protected':{p:self.identity(p) for p in self.p['files']}}

    def boot_prepare(self):
        with self.lock():
            # First remove stale injection. All compatibility failures then fall through to the original chain.
            self.clear_environment()
            try:
                if not self.owned_hook():return {'startup':'DISABLED'}
                state=self.state();self.gate(state)
                if not state or not state.get('enabled'):return {'startup':'DISABLED'}
                result=self.check()
                if result['compatibility']!='PASS':raise Refused('官方接口已足够，不再注入兼容库')
                if self.identity(self.library)['sha256']!=self.p['candidate_sha256']:raise Refused('安装库身份不符')
                if state['phase'] not in ('loaded','startup_prepared') and not (state['phase']=='switching' and self.owner_alive(state)):
                    raise Refused('未关闭的失败或切换事务，禁止启动注入')
                boot=self.host.info()['boot']
                if state['baseline']['boot']!=boot:
                    self.archive(state);state['baseline']=self.boot_baseline()
                self.verify_recovery(state['baseline'])
                state['trial_boots']=list(dict.fromkeys(state.get('trial_boots',[])+[boot]))
                # Reserve the install transaction through ExecStart, while allowing a normal boot to prepare.
                phase='switching' if state['phase']=='switching' else 'startup_prepared'
                state.update(phase=phase,startup='PREPARED',startup_boot=boot)
                self.save_auto(state)
                self.inject_environment()
                return {'startup':'PREPARED','boot':boot,'actual_loading':'NOT_VERIFIED'}
            except (Refused,InstallRefused,OSError,ValueError,KeyError,RuntimeError) as error:
                self.clear_environment()
                try:
                    state=self.state()
                    if state:state.update(startup='SKIPPED',startup_reason=str(error));self.save_auto(state)
                except Exception:pass
                return {'startup':'SKIPPED','reason':str(error),'actual_loading':'NOT_VERIFIED'}

    def status(self):
        state=self.state();service=self.host.service();hook=self.owned_hook()
        loaded=service['active'] and service['loaded']==self.library and self.identity(self.library)['sha256']==self.p['candidate_sha256']
        return {'enabled':bool(state and state.get('enabled') and hook),'loaded':bool(loaded),
            'phase':state['phase'] if state else 'not_managed','startup':state.get('startup','NOT_VERIFIED') if state else 'NOT_VERIFIED',
            'autostart_verified':bool(self.verified and self.p.get('nas_tool_verified') is True),'transcode':'NOT_VERIFIED','boot':self.host.info()['boot']}

    def enable(self):
        with self.lock():
            old=self.state();self.require_closed_transaction(old);self.gate(old);result=self.check()
            if result['compatibility']!='PASS':raise Refused('官方接口已满足，无需安装兼容补丁')
            hook=self.owned_hook()
            if hook:
                if not old or not old.get('enabled') or old['phase'] in ('switching','restoring','recovery_required'):
                    raise Refused('已有未关闭的自动启用事务，先恢复')
                self.verify_recovery(old['baseline'])
                if self.status()['loaded']:return {'operation':'ALREADY_LOADED',**self.status()}
                raise Refused('启动配置存在但未加载，先暂停并检查')
            baseline=self.snapshot();self.host.idle()
            baseline['proof']='ACTUAL_SERVICE_BEFORE_INSTALL'
            library=self.path(self.library)
            if library.exists():
                if self.identity(self.library)['sha256']!=self.p['candidate_sha256']:raise Refused('已有运行库漂移')
            else:
                library.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
                with library.open('xb') as stream:stream.write((self.bundle/'libavcodec.so.62').read_bytes());stream.flush();os.fsync(stream.fileno())
                os.chmod(library,0o644)
                Installer(self.root,required_uid=self.uid).record_library(self.library)
            self.host.load_check(library,self.p);self.archive(old)
            state={'schema':1,'profile':self.p['id'],'enabled':True,'phase':'prepared','baseline':baseline,
                'trial_boots':[self.host.info()['boot']],'transaction':uuid.uuid4().hex,'startup':'NOT_VERIFIED','owner':self.owner()}
            try:
                self.save_auto(state);self.clear_environment();self.write(AUTO_DROPIN,HOOK);os.chmod(self.path(AUTO_DROPIN),0o644)
                state['phase']='switching';self.save_auto(state)
            except Exception:
                self.clear_environment()
                hook_path=self.path(AUTO_DROPIN)
                if hook_path.exists():
                    identity=self.identity(AUTO_DROPIN)
                    if identity['uid']!=self.uid or identity['sha256']!=sha(HOOK) or identity['mode'] not in (0o600,0o644):
                        raise Refused('失败后的启动覆盖身份未知，保留并停止')
                    hook_path.unlink();self.reload_without_hook()
                state.update(enabled=False,phase='aborted_before_restart')
                try:self.save_auto(state)
                except OSError:pass
                raise
        # Release the lock before systemctl waits for our ExecStartPre hook.
        try:
            self.host.restart()
            with self.lock():
                current=self.state()
                if current['transaction']!=state['transaction']:raise Refused('重启期间事务身份变化')
                self.verify_recovery(current['baseline'])
                if not self.status()['loaded']:raise Refused('重启未加载预期候选')
                current['phase']='loaded';self.save_auto(current)
            return {'operation':'AUTO_ENABLED',**self.status()}
        except Exception as error:
            try:
                recovery_result=self.disable(recovering=True)
                if recovery_result['operation']!='RESTORED':raise Refused('仅撤销配置，实际基线未恢复')
            except Exception as recovery:
                current=self.state() or state;current['phase']='recovery_required';self.save_auto(current)
                raise RuntimeError('启用失败且恢复失败，保留记录并停止') from recovery
            raise RuntimeError('启用失败，已恢复当前开机基线：'+str(error)) from error

    def require_closed_transaction(self,state=None):
        state=self.state() if state is None else state
        if state and state['phase'] in ('switching','restoring','recovery_required'):
            raise Refused('服务切换或恢复事务未关闭，先完成恢复')

    def disable(self,recovering=False):
        with self.lock():
            hook=self.owned_hook();state=self.state()
            unfinished=state and state['phase'] in ('restoring','recovery_required')
            if not hook and not unfinished:return {'operation':'ALREADY_INACTIVE',**self.status()}
            if not state:raise Refused('没有恢复合同，拒绝猜测')
            if not recovering and state['phase'] in ('switching','restoring') and self.owner_alive(state):raise Refused('服务切换尚未结束')
            self.host.idle()
            try:self.verify_recovery(state['baseline'])
            except Refused as error:
                # Revoke only the identified hook. Never replay another boot or changed baseline.
                self.archive(state);self.clear_environment()
                if hook:self.path(AUTO_DROPIN).unlink()
                self.reload_without_hook()
                state.update(enabled=False,phase='config_disabled_unverified',startup='DISABLED',reason=str(error));self.save_auto(state)
                return {'operation':'CONFIG_DISABLED_NOT_RESTORED','enabled':False,'actual_loading':'NOT_VERIFIED','reason':str(error)}
            self.archive(state)
            state.update(enabled=False,phase='restoring',owner=self.owner());self.save_auto(state)
            self.clear_environment()
            if hook:self.path(AUTO_DROPIN).unlink()
        try:
            self.host.restart()
            with self.lock():
                self.verify_recovery(state['baseline']);service=self.host.service();baseline=state['baseline']
                if not service['active'] or service['loaded']!=baseline['loaded'] or service['environment']!=baseline['environment'] or service.get('environment_sha256')!=baseline.get('environment_sha256'):
                    raise Refused('恢复后的实际服务映射或环境不符')
                state['phase']='restored';self.save_auto(state)
            return {'operation':'RESTORED',**self.status()}
        except Exception:
            state['phase']='recovery_required';self.save_auto(state);raise
