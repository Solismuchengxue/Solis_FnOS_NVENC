"""Bounded procfs consumer check for an explicitly frozen local action.

Transport argv references may be inherited by its FIFO capture shells.
Actual mappings, descriptors, executable and cwd references always block.
"""
import hashlib,os,re
from pathlib import Path

class ConsumerRefused(RuntimeError):
    pass

class ProcFS:
    def __init__(self,root='/proc'):
        self.root=Path(root)

    def pids(self):
        return [int(p.name) for p in self.root.iterdir() if p.name.isdigit()]

    def read(self,pid,name):
        limit=8*1024*1024 if name=='maps' else 128*1024
        with (self.root/str(pid)/name).open('rb') as stream:data=stream.read(limit+1)
        if len(data)>limit:raise ConsumerRefused('进程元数据超过读取上限：'+str(pid))
        return data

    def meta(self,pid):
        p=self.root/str(pid);words=self.read(pid,'stat').decode().split(') ',1)[1].split()
        return {'parent':int(words[1]),'start':words[19],'uid':p.stat().st_uid}

    def comm(self,pid):
        return self.read(pid,'comm').decode().strip()

    def link(self,pid,name):
        value=os.readlink(self.root/str(pid)/name)
        if value.endswith(' (deleted)'):value=value[:-10]
        return Path(value).resolve() if value.startswith('/') else None

    def fds(self,pid):
        for entry in (self.root/str(pid)/'fd').iterdir():
            try:
                path=self.link(pid,'fd/'+entry.name)
                if path is not None:yield path
            except FileNotFoundError:continue

def assert_no_consumers(roots,helper_argv,helper_exe_sha256,proc=None,helper_uid=None):
    """Check all processes; exempt only inherited argv of this frozen action.

    Callers freeze the exact helper argv, interpreter SHA and outer SSH UID.
    No caller-supplied PID or wildcard process/user whitelist is accepted.
    """
    proc=proc or ProcFS();roots=tuple(Path(p) for p in roots)
    for root in roots:
        if not root.is_absolute() or root.resolve(strict=True)!=root or not root.is_dir():
            raise ConsumerRefused('清理根不是已存在的规范目录')
        if any(p.is_symlink() for p in (root,*root.parents)):raise ConsumerRefused('清理路径含符号链接')
    if not helper_argv or not re.fullmatch('[0-9a-f]{64}',helper_exe_sha256):raise ConsumerRefused('控制合同缺失')
    expected=b'\0'.join(os.fsencode(a) for a in helper_argv)+b'\0'
    observed={};ancestors=set();pid=os.getpid()
    def meta(pid):
        value=proc.meta(pid)
        previous=observed.setdefault(pid,value)
        if previous!=value:raise ConsumerRefused('进程身份或亲缘变化：'+str(pid))
        return value
    for _ in range(64):
        if pid in ancestors:raise ConsumerRefused('进程祖先循环')
        ancestors.add(pid);m=meta(pid)
        if pid==1 or m['parent']==0:break
        pid=m['parent']
    else:raise ConsumerRefused('进程亲缘超过上限')
    def same_shell(pid,uid):
        if meta(pid)['uid']!=uid or proc.read(pid,'cmdline')!=expected:return False
        executable=proc.link(pid,'exe')
        return executable is not None and hashlib.sha256(executable.read_bytes()).hexdigest()==helper_exe_sha256
    anchors=[]
    for pid in ancestors:
        if same_shell(pid,meta(pid)['uid']) and (helper_uid is None or meta(pid)['uid']==helper_uid):anchors.append(pid)
    if len(anchors)!=1:raise ConsumerRefused('无法唯一绑定当前控制链路')
    anchor=anchors[0];uid=meta(anchor)['uid'];family=set(ancestors)
    def inherited_capture(pid):
        chain=[]
        for _ in range(64):
            if pid==anchor:
                family.update(chain);return True
            if pid in chain or not same_shell(pid,uid):return False
            chain.append(pid);pid=meta(pid)['parent']
            if pid<=0:return False
        return False
    def inside(path):
        return path is not None and any(path==root or root in path.parents for root in roots)
    # A component boundary prevents P_other from being mistaken for P.
    mentions=[re.compile(re.escape(os.fsencode(str(root)))+rb'(?=$|[/\x00\s\x22\x27])') for root in roots]
    checked=0;control_references=0
    for pid in proc.pids():
        try:
            meta(pid);checked+=1
            for line in proc.read(pid,'maps').splitlines():
                fields=line.split(None,5)
                if len(fields)==6 and fields[5].startswith(b'/'):
                    value=os.fsdecode(fields[5])
                    if value.endswith(' (deleted)'):value=value[:-10]
                    if inside(Path(value).resolve()):raise ConsumerRefused('临时目录仍有库/文件映射：'+str(pid))
            for name in ('cwd','exe'):
                try:path=proc.link(pid,name)
                except FileNotFoundError:path=None
                if inside(path):raise ConsumerRefused('临时目录仍是进程工作目录/程序：'+str(pid))
            if any(inside(path) for path in proc.fds(pid)):raise ConsumerRefused('临时文件仍有打开句柄：'+str(pid))
            raw=proc.read(pid,'cmdline')
            if any(pattern.search(raw) for pattern in mentions):
                if pid in ancestors or inherited_capture(pid):control_references+=1
                else:raise ConsumerRefused('仍有真实外部临时目录消费者：'+str(pid))
            meta(pid)
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError as e:raise ConsumerRefused('无法核对进程：'+str(pid)) from e
    for pid,identity in observed.items():
        try:
            if proc.meta(pid)!=identity:raise ConsumerRefused('核对期间进程身份变化：'+str(pid))
        except (FileNotFoundError,ProcessLookupError):continue
    return {'result':'PASS','processes_checked':checked,'bound_control_processes':len(family),'inherited_control_references':control_references,'external_consumers':0,'resource_consumers':0}
