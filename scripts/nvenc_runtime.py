"""Single-service compatibility controller. CLI has no remote or test-root mode."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import stat
import subprocess
import sys
import time

DROPIN = "/run/systemd/system/mediasrv.service.d/95-solis-nvenc-managed.conf"
STATE = "/var/lib/solis-fnos-nvenc/state.json"
PREFIX = "/opt/solis-fnos-nvenc/managed"

class Refused(RuntimeError): pass

def sha(data): return hashlib.sha256(data).hexdigest()

class Controller:
    def __init__(self, root, bundle, profile, host, trial=None):
        self.root=Path(root);self.bundle=Path(bundle);self.p=profile;self.host=host
        self.trial=trial
        self.library=PREFIX+"/"+profile["candidate_sha256"]+"/libavcodec.so.62"

    def path(self, absolute):
        if not absolute.startswith('/') or '..' in Path(absolute).parts: raise Refused("路径越界")
        p=self.root/absolute.lstrip('/')
        for item in (p,*p.parents):
            if item==self.root.parent:break
            if item.is_symlink():raise Refused("路径含符号链接："+absolute)
        return p

    def identity(self, absolute):
        p=self.path(absolute)
        try:
            st=p.stat()
            if not stat.S_ISREG(st.st_mode):raise Refused("非普通文件："+absolute)
            return {"sha256":sha(p.read_bytes()),"size":st.st_size,"mode":stat.S_IMODE(st.st_mode),"uid":st.st_uid,"gid":st.st_gid}
        except OSError as e: raise Refused("文件不可读："+absolute) from e

    def write(self, absolute, data):
        p=self.path(absolute);p.parent.mkdir(parents=True,exist_ok=True)
        self.path(absolute)
        scratch=p.with_name(p.name+".new")
        # A previous interrupted write is evidence, never silently overwrite it.
        with scratch.open('xb') as f:
            os.chmod(scratch,0o600);f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(scratch,p)

    def read_state(self,allow_inactive_previous=False):
        p=self.path(STATE)
        if not p.exists():return None
        s=json.loads(p.read_text())
        if s.get("schema")!=1:raise Refused("恢复记录版本不匹配")
        if s.get("profile")!=self.p["id"]:
            # Old records may be preserved, never replayed, after an approved upgrade.
            if not allow_inactive_previous or self.path(DROPIN).exists():raise Refused("恢复记录版本不匹配")
        return s

    def save(self,s):self.write(STATE,(json.dumps(s,ensure_ascii=False,indent=2)+'\n').encode())

    def component_check(self):
        info=self.host.info()
        for key in ("arch","os","glibc","gpu"):
            if info[key]!=self.p[key]:raise Refused("未知或不兼容的版本："+key)
        for path,expected in self.p["files"].items():
            if self.identity(path)["sha256"]!=expected:raise Refused("系统/影视组件已变化："+path)
        return info

    def static_check(self):
        info=self.component_check()
        if info["driver"]!=self.p["driver"]:raise Refused("未知或不兼容的版本：driver")
        if info["api"]<self.p["candidate_api"]:raise Refused("驱动 NVENC API 不足")
        candidate=self.bundle/"libavcodec.so.62"
        if candidate.is_symlink() or not candidate.is_file() or sha(candidate.read_bytes())!=self.p["candidate_sha256"]:
            raise Refused("私人制品缺失或 SHA256 不符")
        deps=self.host.load_check(candidate,self.p)
        if deps.get("abi")!=62 or deps.get("deps")!="PASS":raise Refused("ABI/依赖加载不匹配")
        expected=self.p.get("dependencies")
        if not isinstance(expected,dict):raise Refused("NAS 外部依赖身份尚未冻结，停止并请负责人核对")
        if deps.get("identities",{})!=expected:raise Refused("未知或变化的外部依赖，停止部署")
        return info,deps

    def check(self):
        info=self.component_check()
        if info["api"]>=self.p["official_api"]:
            return {"compatibility":"OFFICIAL_API_SUFFICIENT","profile":self.p["id"],"transcode":"NOT_VERIFIED","message":"已知官方组件的接口条件已满足，先使用官方影视，无需部署兼容库；这不是原生实测通过"}
        info,deps=self.static_check()
        return {"compatibility":"OFFICIAL_API_SUFFICIENT" if info["api"]>=self.p["official_api"] else "PASS", "profile":self.p["id"],"dependencies":deps,"nas_tool_verified":self.p["nas_tool_verified"],"fnos_marketing_version":self.p.get("fnos_marketing_version","UNKNOWN"),"transcode":"NOT_VERIFIED"}

    def snapshot(self):
        info,_=self.static_check();service=self.host.service()
        if not service["active"]:raise Refused("影视服务未正常运行")
        loaded=service["loaded"]
        expected=self.p["allowed_baseline"].get(loaded)
        if not expected or self.identity(loaded)["sha256"]!=expected:raise Refused("当前可用库身份未知")
        dropins={}
        for path in service["dropins"]:
            expected=self.p["allowed_dropins"].get(path)
            if not expected or self.identity(path)["sha256"]!=expected:raise Refused("存在未知服务覆盖："+path)
            dropins[path]=self.identity(path)
        return {"boot":info["boot"],"loaded":loaded,"loaded_identity":self.identity(loaded),"environment":service["environment"],"environment_sha256":service.get("environment_sha256"),"dropins":dropins,"protected":{p:self.identity(p) for p in self.p["files"]},"dependencies":self.host.load_check(self.bundle/"libavcodec.so.62",self.p)}

    def verify_baseline_files(self,b):
        info=self.component_check()
        if info["driver"]!=self.p["driver"] or info["api"]<self.p["candidate_api"]:raise Refused("驱动身份发生漂移")
        if info["boot"]!=b["boot"]:raise Refused("重启后恢复点失效，需重新检查")
        for path,identity in {**b["protected"],**b["dropins"],b["loaded"]:b["loaded_identity"]}.items():
            if self.identity(path)!=identity:raise Refused("当次基线发生漂移："+path)
        for path,expected in b["dependencies"].get("identities",{}).items():
            if self.identity(path)["sha256"]!=expected:raise Refused("依赖发生漂移："+path)
        expected=set(b["dropins"])
        if self.path(DROPIN).exists():expected.add(DROPIN)
        if set(self.host.service()["dropins"])!=expected:raise Refused("服务覆盖集合发生漂移")

    def owned_dropin(self,s):
        p=self.path(DROPIN)
        if not p.is_file() or sha(p.read_bytes())!=s["dropin_sha256"]:raise Refused("本工具覆盖身份不符")

    def status(self):
        self.component_check()
        s=self.read_state(allow_inactive_previous=True);service=self.host.service();installed=self.path(self.library).exists()
        intact=installed and self.identity(self.library)["sha256"]==self.p["candidate_sha256"]
        loaded=service["active"] and service["loaded"]==self.library and intact
        return {"installed":bool(intact),"loaded":bool(loaded),"transcode":"NOT_VERIFIED","phase":s["phase"] if s else "not_managed","nas_tool_verified":self.p["nas_tool_verified"]}

    def deploy(self):
        result=self.check()
        if result["compatibility"]=="OFFICIAL_API_SUFFICIENT":raise Refused("官方 NVENC 接口条件已满足，请先使用官方组件，无需本补丁")
        if not self.p["nas_tool_verified"]:
            if not self.trial:raise Refused("本工具尚未完成 NAS 单独验证，停止部署")
            t=self.trial
            digest=sha(json.dumps(self.p,sort_keys=True,separators=(',',':')).encode())
            if t.get('schema')!=1 or not t.get('authorization_id') or t.get('profile_sha256')!=digest:raise Refused('试用合同/版本身份不符')
            now=time.time()
            if not now<t.get('expires_at',0)<=now+3600 or t.get('boot')!=self.host.info()['boot']:raise Refused('试用合同已过期或 boot 变化')
        s=self.read_state(allow_inactive_previous=True);drop=self.path(DROPIN)
        if drop.exists():
            if not s:raise Refused("已有同名覆盖，无法确认消费者")
            self.owned_dropin(s);self.verify_baseline_files(s["baseline"])
            if self.status()["loaded"]:return {"operation":"ALREADY_LOADED",**self.status()}
            raise Refused("覆盖存在但服务未加载，先回退并检查")
        if s and s["phase"]=="recovery_required":raise Refused("上次恢复失败，保留证据并求助")
        baseline=self.snapshot();self.host.idle()
        if not self.p['nas_tool_verified']:
            if s and s.get('trial_authorization_id')==self.trial['authorization_id']:raise Refused('试用已经结束，不允许重放')
            if baseline!=self.trial.get('baseline'):raise Refused('试用实际基线发生漂移')
        lib=self.path(self.library)
        if lib.exists():
            if self.identity(self.library)["sha256"]!=self.p["candidate_sha256"]:raise Refused("安装目录制品漂移")
        else:
            lib.parent.mkdir(parents=True,exist_ok=True)
            self.path(self.library)
            with lib.open('xb') as f:f.write((self.bundle/"libavcodec.so.62").read_bytes());f.flush();os.fsync(f.fileno())
            os.chmod(lib,0o644)
        if self.identity(self.library)["sha256"]!=self.p["candidate_sha256"]:raise Refused("复制期间制品发生漂移；未切换服务")
        self.host.load_check(lib,self.p)
        content=("[Service]\nEnvironment=\"LD_LIBRARY_PATH="+str(Path(self.library).parent)+":"+self.p["official_dir"]+":/usr/trim/lib\"\n").encode()
        s={"schema":1,"profile":self.p["id"],"phase":"prepared","baseline":baseline,"dropin_sha256":sha(content),"library":self.library}
        if not self.p['nas_tool_verified']:s['trial_authorization_id']=self.trial['authorization_id']
        previous=self.path(STATE)
        if previous.exists():
            data=previous.read_bytes()
            saved=STATE.rsplit('/',1)[0]+"/previous-"+sha(data)+".json"
            if not self.path(saved).exists():self.write(saved,data)
            elif self.path(saved).read_bytes()!=data:raise Refused("上次恢复记录存档冲突")
        self.save(s)
        wrote_dropin=False
        try:
            self.verify_baseline_files(baseline)
            # Recheck effective state before writing a service override.
            current=self.host.service()
            if current["environment"]!=baseline["environment"] or current["loaded"]!=baseline["loaded"]:raise Refused("服务基线发生漂移")
            self.host.idle();self.write(DROPIN,content);wrote_dropin=True;os.chmod(self.path(DROPIN),0o644)
            s["phase"]="switching";self.save(s);self.host.restart()
            self.verify_baseline_files(baseline)
            if not self.status()["loaded"]:raise RuntimeError("服务未加载候选")
            s["phase"]="loaded";self.save(s)
            return {"operation":"DEPLOYED",**self.status()}
        except Exception as e:
            if not wrote_dropin:
                s["phase"]="aborted_before_switch";self.save(s)
                raise Refused("未切换服务；停止："+str(e)) from e
            try:
                self.restore(s,"restored_after_failure")
            except Exception as recovery:
                s["phase"]="recovery_required";self.save(s)
                raise RuntimeError("自动恢复失败；保留恢复记录，停止并求助") from recovery
            raise RuntimeError("部署失败；已恢复当次实际基线") from e

    def restore(self,s,phase):
        b=s["baseline"];self.verify_baseline_files(b)
        drop=self.path(DROPIN)
        if drop.exists():
            self.owned_dropin(s)
            retired=self.path(STATE).parent/("retired-"+s["dropin_sha256"]+".conf")
            if retired.exists() and retired.read_bytes()!=drop.read_bytes():raise Refused("退役证据冲突")
            if not retired.exists():retired.write_bytes(drop.read_bytes());os.chmod(retired,0o600)
            drop.unlink()
        self.host.restart()
        service=self.host.service()
        self.verify_baseline_files(b)
        if not service["active"] or service["loaded"]!=b["loaded"] or service["environment"]!=b["environment"] or service.get("environment_sha256")!=b.get("environment_sha256") or set(service["dropins"])!=set(b["dropins"]):
            raise RuntimeError("恢复后的服务/环境/映射不符合当次基线")
        s["phase"]=phase;self.save(s)

    def rollback(self):
        if not self.path(DROPIN).exists():return {"operation":"ALREADY_INACTIVE",**self.status()}
        s=self.read_state()
        if not s:raise Refused("缺少当次恢复记录，拒绝猜测回退")
        self.host.idle();self.owned_dropin(s);self.verify_baseline_files(s["baseline"])
        try:self.restore(s,"restored")
        except Exception as e:
            s["phase"]="recovery_required";self.save(s)
            raise RuntimeError("回退恢复失败，保留记录并停止求助") from e
        return {"operation":"RESTORED",**self.status()}

def run(argv,env=None):
    r=subprocess.run(argv,capture_output=True,text=True,timeout=30,env=env)
    if r.returncode:raise Refused("检查命令失败："+Path(argv[0]).name)
    return r.stdout.strip()

class LinuxHost:
    def info(self):
        if sys.platform!="linux":raise Refused("仅支持 Linux NAS；Windows 请运行本地测试")
        values=dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        driver=run(['nvidia-smi','--query-gpu=driver_version','--format=csv,noheader'])
        api=ctypes.c_uint32()
        library=ctypes.CDLL('libnvidia-encode.so.1')
        f=library.NvEncodeAPIGetMaxSupportedVersion;f.argtypes=[ctypes.POINTER(ctypes.c_uint32)];f.restype=ctypes.c_int
        if f(ctypes.byref(api))!=0:raise Refused("驱动接口检查失败")
        gpu=run(['nvidia-smi','--query-gpu=name','--format=csv,noheader'])
        return {"arch":platform.machine(),"os":values.get('VERSION_ID','').strip('"'),"glibc":platform.libc_ver()[1],"driver":driver,"gpu":gpu,"api":api.value,"boot":Path('/proc/sys/kernel/random/boot_id').read_text().strip()}

    def service(self):
        values=dict(line.split('=',1) for line in run(['systemctl','show','mediasrv','-p','ActiveState','-p','MainPID','-p','Environment','-p','DropInPaths','-p','FragmentPath']).splitlines() if '=' in line)
        if values.get('FragmentPath')!='/etc/systemd/system/mediasrv.service':raise Refused("服务入口未知")
        pid=int(values.get('MainPID','0'));loaded=[]
        if pid:
            for line in Path(f'/proc/{pid}/maps').read_text().splitlines():
                parts=line.split(None,5)
                if len(parts)==6 and Path(parts[5]).name=='libavcodec.so.62':loaded.append(parts[5])
        loaded=set(loaded)
        if pid and len(loaded)!=1:raise Refused("服务 codec 映射不唯一")
        raw_environment=values.get('Environment','')
        ld=[v for v in shlex.split(raw_environment) if v.startswith('LD_LIBRARY_PATH=')]
        if len(ld)>1:raise Refused("服务库路径不唯一")
        # Persist only the nonsecret library path and a digest, never arbitrary environment values.
        return {"active":values.get('ActiveState')=='active',"pid":pid,"environment":ld[0] if ld else '',"environment_sha256":sha(raw_environment.encode()),"loaded":next(iter(loaded),''),"dropins":values.get('DropInPaths','').split()}

    def idle(self):
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                if (p/'comm').read_text().strip()=='ffmpeg':raise Refused("仍有 ffmpeg 播放/转码进程，请停止后重试")
            except (FileNotFoundError,ProcessLookupError):continue
        counts=run(['nvidia-smi','--query-gpu=encoder.stats.sessionCount','--format=csv,noheader'])
        if any(int(n.strip()) for n in counts.splitlines()):raise Refused("GPU 转码仍在运行")

    def load_check(self,lib,profile):
        env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LANG":"C","LD_LIBRARY_PATH":profile["official_dir"]+":/usr/trim/lib"}
        dynamic=run(['readelf','-d',str(lib)],env)
        if 'Library soname: [libavcodec.so.62]' not in dynamic:raise Refused("SONAME 不匹配")
        versions=run(['readelf','--version-info',str(lib)],env)
        for word in versions.split():
            if word.startswith('GLIBC_'):
                nums=word[6:].split('.')
                if all(n.isdigit() for n in nums) and tuple(map(int,nums))>(2,36):raise Refused("glibc ABI 要求过高")
        lines=run(['ldd',str(lib)],env)
        if 'not found' in lines:raise Refused("依赖缺失")
        dependencies={}
        for line in lines.splitlines():
            words=line.split()
            location=words[2] if '=>' in words and len(words)>2 else (words[0] if words else '')
            if location.startswith('/'):
                p=Path(location).resolve(strict=True)
                if not p.is_file():raise Refused("依赖不是普通文件")
                dependencies[str(p)]=sha(p.read_bytes())
        if not isinstance(profile.get('dependencies'),dict):raise Refused("NAS 外部依赖身份尚未冻结，停止并请负责人核对")
        if dependencies!=profile['dependencies']:raise Refused("外部依赖身份与已核对组合不符")
        code='import ctypes,sys;c=ctypes.CDLL(sys.argv[1]);c.avcodec_version.restype=ctypes.c_uint;print(c.avcodec_version()>>16)'
        abi=int(run([sys.executable,'-B','-c',code,str(lib)],env))
        return {"abi":abi,"deps":"PASS","identities":dependencies}

    def restart(self):
        run(['systemctl','daemon-reload']);run(['systemctl','restart','mediasrv'])
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            try:
                service=self.service()
                if service['active'] and service['pid'] and service['loaded']:return service
            except Refused:
                pass
            time.sleep(0.2)
        raise Refused('重启后实际库映射未就绪')

def human_result(result):
    if result.get('compatibility')=='OFFICIAL_API_SUFFICIENT':
        return '官方 NVENC 接口条件已满足，先使用官方影视，无需部署兼容库。原生播放仍需核对。'
    lines=[]
    if 'compatibility' in result:
        lines.append('兼容检查：已知组件、接口和依赖相符。')
    operations={'DEPLOYED':'临时部署完成，影视服务已重启。','ALREADY_LOADED':'同一版本已加载，无需再次重启。','RESTORED':'已恢复本次部署前的实际可用版本。','ALREADY_INACTIVE':'当前没有本工具覆盖，无需回退。'}
    if 'operation' in result:lines.append(operations[result['operation']])
    if 'installed' in result:lines.append('安装：'+('已安装' if result['installed'] else '未安装'))
    if 'loaded' in result:lines.append('服务加载：'+('已加载' if result['loaded'] else '未加载'))
    lines.append('转码验证：尚未验证，需要原生播放实测。')
    if not result.get('nas_tool_verified',False):lines.append('NAS 工具验证：未完成，部署与回退入口尚未开放。')
    return '\n'.join(lines)

def main():
    parser=argparse.ArgumentParser(description="fnOS NVENC：检查、临时部署、状态、回退。真实 NAS 验证后才开放部署。")
    parser.add_argument('action',choices=['check','deploy','status','rollback'])
    args=parser.parse_args()
    if sys.platform!='linux' or os.geteuid()!=0:raise Refused("请在 NAS 使用 sudo；本地验证只运行测试文件")
    project=Path(__file__).resolve().parents[1]
    p=json.loads((project/'docs/runtime_profile.json').read_text())
    c=Controller(Path('/'),project/'artifacts/runtime_bundle',p,LinuxHost())
    if args.action in ('deploy','rollback'):
        if not p['nas_tool_verified']:
            trial_path=c.path(str(project/'artifacts/runtime_bundle/trial_authorization.json'))
            if not trial_path.is_file():raise Refused("工具未完成 NAS 验证；没有当次试用合同，停止运行变更")
            st=trial_path.stat()
            if st.st_uid!=0 or stat.S_IMODE(st.st_mode)!=0o600:raise Refused('试用合同权限不符')
            c.trial=json.loads(trial_path.read_text())
        import fcntl
        lock=c.path('/run/lock/solis-nvenc.lock')
        fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=getattr(c,args.action)()
    else:result=getattr(c,args.action)()
    print(human_result(result))
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (Refused,OSError,RuntimeError,ValueError,KeyError,subprocess.TimeoutExpired) as e:
        print('STOP：'+str(e),file=sys.stderr);sys.exit(1)
