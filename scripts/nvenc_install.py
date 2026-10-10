# SPDX-License-Identifier: GPL-3.0-or-later
"""Inventory-owned installation. Unknown files and consumers stop retirement."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import uuid

class InstallRefused(RuntimeError):pass

def sha(data):return hashlib.sha256(data).hexdigest()

def safe(path):
    path=Path(path).absolute()
    if '..' in path.parts or any(p.is_symlink() for p in (path,*path.parents)):
        raise InstallRefused('安装路径含符号链接或越界')
    return path

def relative(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or not path.parts:
        raise InstallRefused('清单路径越界')
    return path

def inventory(folder,files=None):
    folder=safe(folder)
    if files is None:
        files=[]
        for path in folder.rglob('*'):
            if path.is_symlink():raise InstallRefused('安装树含符号链接')
            if path.is_file():files.append(path.relative_to(folder).as_posix())
            elif not path.is_dir():raise InstallRefused('安装树含特殊文件')
    result={}
    for name in sorted(files):
        path=safe(folder/relative(name));info=path.stat()
        if not stat.S_ISREG(info.st_mode):raise InstallRefused('清单项目不是普通文件')
        data=path.read_bytes();result[name]={'sha256':sha(data),'bytes':len(data)}
    return result

def atomic_bytes(path,data):
    path=safe(path);path.parent.mkdir(parents=True,exist_ok=True)
    scratch=path.with_name(path.name+'.new-'+uuid.uuid4().hex)
    with scratch.open('xb') as stream:
        os.chmod(scratch,0o600);stream.write(data);stream.flush();os.fsync(stream.fileno())
    os.replace(scratch,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def atomic_json(path,value):
    atomic_bytes(path,(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())

class Installer:
    def __init__(self,root=Path('/'),required_uid=0):
        self.root=safe(root);self.base=safe(self.root/'opt/solis-fnos-nvenc/tool');self.uid=required_uid

    def secure(self,path):
        path=safe(path)
        for item in (path,*path.parents):
            info=item.stat()
            if info.st_uid!=self.uid or stat.S_IMODE(info.st_mode)&0o022:
                raise InstallRefused('安装材料所有权或写权限不符：'+str(item))
            if item==self.root:break
        return path

    def record_library(self,absolute):
        if not re.fullmatch(r'/opt/solis-fnos-nvenc/managed/[a-f0-9]{64}/libavcodec\.so\.62',absolute):
            raise InstallRefused('库路径不属于安装器')
        path=self.secure(self.root/absolute.lstrip('/'));info=path.stat()
        identity={'sha256':sha(path.read_bytes()),'bytes':info.st_size,'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid}
        record=self.root/'var/lib/solis-fnos-nvenc/library_ownership.json'
        value=json.loads(self.secure(record).read_text()) if record.exists() else {'schema':1,'project':'Solis_FnOS_NVENC','files':{}}
        if value.get('schema')!=1 or value.get('project')!='Solis_FnOS_NVENC':raise InstallRefused('库所有权清单未知')
        if absolute in value['files'] and value['files'][absolute]!=identity:raise InstallRefused('已记录的库身份漂移')
        value['files'][absolute]=identity;atomic_json(record,value)

    def owned_libraries(self):
        record=self.root/'var/lib/solis-fnos-nvenc/library_ownership.json'
        if not record.exists():return []
        value=json.loads(self.secure(record).read_text())
        if value.get('schema')!=1 or value.get('project')!='Solis_FnOS_NVENC':raise InstallRefused('库所有权清单未知')
        paths=[]
        for absolute,expected in value['files'].items():
            if not re.fullmatch(r'/opt/solis-fnos-nvenc/managed/[a-f0-9]{64}/libavcodec\.so\.62',absolute):raise InstallRefused('库清单路径越界')
            path=safe(self.root/absolute.lstrip('/'))
            if not path.exists():continue
            info=self.secure(path).stat()
            actual={'sha256':sha(path.read_bytes()),'bytes':info.st_size,'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid}
            if actual!=expected:raise InstallRefused('自有库身份变化，保留并停止')
            if set(path.parent.iterdir())!={path}:raise InstallRefused('自有库目录包含未知材料')
            paths.append(path)
        return paths

    def known_base(self,refuse_staging=False):
        self.secure(self.base)
        owner=self.secure(self.base/'owner.json')
        if json.loads(owner.read_text())!={'project':'Solis_FnOS_NVENC','schema':1}:
            raise InstallRefused('不是本工具管理的安装目录')
        if refuse_staging and any(p.name.startswith('.staging-') for p in self.base.iterdir()):
            raise InstallRefused('存在未完成安装目录，保留并停止')
        allowed={'owner.json','current.json','previous.json','releases','runner.sh','bootstrap.py','bootstrap.json'}
        if any(p.name not in allowed and not p.name.startswith('.staging-') for p in self.base.iterdir()):raise InstallRefused('工具根含未知材料')

    def current(self):
        self.known_base();pointer=self.secure(self.base/'current.json')
        value=json.loads(pointer.read_text());self.verify_pointer(value)
        return value

    def verify_pointer(self,value):
        release=value['release']
        if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{16}',release):
            raise InstallRefused('版本指针越界')
        directory=self.secure(self.base/'releases'/release)
        manifest=json.loads(self.secure(directory/'manifest.json').read_text())
        if manifest['release']!=release or sha((directory/'manifest.json').read_bytes())!=value['manifest_sha256']:
            raise InstallRefused('安装版本清单身份不符')
        actual=inventory(directory);actual.pop('manifest.json',None)
        if actual!=manifest['files']:raise InstallRefused('安装文件漂移或多出未知材料')
        for path in directory.rglob('*'):self.secure(path)
        if (self.base/'bootstrap.json').exists():
            expected=json.loads(self.secure(self.base/'bootstrap.json').read_text())
            if inventory(self.base,expected.keys())!=expected:raise InstallRefused('稳定启动入口身份不符')
            for name in expected:self.secure(self.base/name)
        return value

    def adopt_legacy(self):
        # Required identity gates; the entire old tree is retained, never removed.
        required={'fnos-nvenc.sh':'40384f2100e232354b94ea1cf8330ad2ce5c4201478db6f1d83f2965466859a2',
            'scripts/nvenc_runtime.py':'1250a7a648e9bc94709d250f11e11ee8b1447bdf3b70ff6356cb0762bd78f1cf',
            'docs/runtime_profile.json':'7500837c57ce9117b746ab6c0f12fa5d18151d4cb38420cf981462f699f7b559',
            'artifacts/runtime_bundle/libavcodec.so.62':'88e48674062ee5ef71864a2619324772bc856fec78c0d4793920fa7d4c15cd57'}
        actual=inventory(self.base)
        for name,expected in required.items():
            if actual.get(name,{}).get('sha256')!=expected:raise InstallRefused('已有工具身份未知，保留并停止')
        for path in (self.base,*self.base.rglob('*')):self.secure(path)
        assert_no_consumers([self.base])
        backup=safe(self.base.parent/'backups'/('legacy-'+sha(json.dumps(actual,sort_keys=True).encode())[:16]))
        if backup.exists():raise InstallRefused('旧工具备份位置已有材料')
        backup.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        os.rename(self.base,backup)
        return backup

    def install(self,source,files,version,adopt=False,bootstrap=None):
        if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version):raise InstallRefused('版本号不合法')
        source=safe(source);expected=inventory(source,files)
        fingerprint=sha(json.dumps({'version':version,'files':expected},sort_keys=True).encode())[:16]
        release=version+'-'+fingerprint;legacy=None
        if self.base.exists():
            if not (self.base/'owner.json').exists():
                if not adopt:raise InstallRefused('已有目录不属于安装器，拒绝覆盖')
                legacy=self.adopt_legacy()
            else:self.current()
        self.base.mkdir(mode=0o700,parents=True,exist_ok=True)
        if not (self.base/'owner.json').exists():atomic_json(self.base/'owner.json',{'project':'Solis_FnOS_NVENC','schema':1})
        self.known_base(refuse_staging=True);self.secure(self.base)
        previous=self.current() if (self.base/'current.json').exists() else None
        if previous and previous['release']==release:return {'operation':'ALREADY_INSTALLED',**previous}
        releases=self.base/'releases';releases.mkdir(mode=0o700,exist_ok=True);self.secure(releases)
        destination=safe(releases/release)
        if destination.exists():
            pointer={'schema':1,'release':release,'manifest_sha256':sha(self.secure(destination/'manifest.json').read_bytes())}
            self.verify_pointer(pointer)
            if json.loads((destination/'manifest.json').read_text())['files']!=expected:raise InstallRefused('已有版本不是本次来源')
            if previous:atomic_json(self.base/'previous.json',previous)
            atomic_json(self.base/'current.json',pointer)
            return {'operation':'SWITCHED_EXISTING',**pointer}
        stage=self.base/('.staging-'+uuid.uuid4().hex);stage.mkdir(mode=0o700)
        try:
            for name,identity in expected.items():
                target=stage/relative(name);target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                with target.open('xb') as stream:stream.write(safe(source/name).read_bytes())
                os.chmod(target,0o600)
                if inventory(stage,[name])[name]!=identity:raise InstallRefused('复制期间材料变化')
            atomic_json(stage/'manifest.json',{'schema':1,'release':release,'version':version,'files':expected})
            if destination.exists():raise InstallRefused('已有版本目录，拒绝覆盖')
            os.rename(stage,destination)
            if bootstrap and not (self.base/'bootstrap.json').exists():
                for name,data in bootstrap.items():
                    if name not in ('runner.sh','bootstrap.py'):raise InstallRefused('稳定入口文件名不合法')
                    with (self.base/name).open('xb') as stream:stream.write(data)
                    os.chmod(self.base/name,0o700 if name.endswith('.sh') else 0o600)
                atomic_json(self.base/'bootstrap.json',inventory(self.base,bootstrap.keys()))
            pointer={'schema':1,'release':release,'manifest_sha256':sha((destination/'manifest.json').read_bytes())}
            if previous:atomic_json(self.base/'previous.json',previous)
            atomic_json(self.base/'current.json',pointer)
            self.current()
            return {'operation':'INSTALLED','legacy_backup':str(legacy) if legacy else None,**pointer}
        except Exception:
            # Never guess cleanup for staging. A known previous pointer remains usable.
            if previous:atomic_json(self.base/'current.json',previous)
            if legacy and not (self.base/'current.json').exists():
                # Keep the failed new tree under its own name; restore the old path.
                failed=safe(self.base.parent/('failed-install-'+uuid.uuid4().hex))
                os.rename(self.base,failed);os.rename(legacy,self.base)
            raise

    def restore_previous(self):
        self.known_base();previous=json.loads(self.secure(self.base/'previous.json').read_text())
        self.verify_pointer(previous)
        current=json.loads(self.secure(self.base/'current.json').read_text())
        history=self.root/'var/lib/solis-fnos-nvenc'/('tool-pointer-history-'+sha(json.dumps(current,sort_keys=True).encode())+'.json')
        if not history.exists():atomic_json(history,current)
        # Preserve a damaged version; only the ordinary pointer changes after verification.
        atomic_json(self.base/'current.json',previous)
        return previous

    def uninstall(self,consumer_check):
        self.current();self.known_base(refuse_staging=True)
        releases=self.base/'releases'
        for path in releases.iterdir():
            if not path.is_dir() or path.is_symlink():raise InstallRefused('版本目录身份未知')
            manifest=json.loads(self.secure(path/'manifest.json').read_text())
            if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{16}',path.name) or manifest['release']!=path.name:
                raise InstallRefused('历史版本名称未知')
            fingerprint=sha(json.dumps({'version':manifest['version'],'files':manifest['files']},sort_keys=True).encode())[:16]
            if path.name!=manifest['version']+'-'+fingerprint:raise InstallRefused('历史清单与版本指纹不符')
            actual=inventory(path);actual.pop('manifest.json',None)
            if actual!=manifest['files']:raise InstallRefused('历史安装版本含漂移或未知材料')
            for item in path.rglob('*'):self.secure(item)
        libraries=self.owned_libraries()
        consumer_check([self.base,*(path.parent for path in libraries)])
        for path in libraries:path.unlink();path.parent.rmdir()
        # The caller also checks library consumers and disables the patch before here.
        for path in sorted(self.base.rglob('*'),key=lambda p:len(p.parts),reverse=True):
            safe(path)
            if path.is_file():path.unlink()
            elif path.is_dir():path.rmdir()
            else:raise InstallRefused('卸载期间出现未知文件')
        self.base.rmdir()
        return {'operation':'TOOL_UNINSTALLED','recovery':'PRESERVED'}

def assert_no_consumers(roots):
    roots=[safe(p) for p in roots]
    def inside(value):return any(value==p or p in value.parents for p in roots)
    ancestors=set();pid=os.getpid()
    for _ in range(64):
        ancestors.add(pid)
        if pid==1:break
        words=Path('/proc',str(pid),'stat').read_text().split(') ',1)[1].split();pid=int(words[1])
        if pid==0:break
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():continue
        try:
            before=(process/'stat').read_bytes()
            for line in (process/'maps').read_text().splitlines():
                fields=line.split(None,5)
                if len(fields)==6 and fields[5].startswith('/') and inside(Path(fields[5].removesuffix(' (deleted)'))):
                    raise InstallRefused('材料仍有进程映射：'+process.name)
            for path in [process/'cwd',process/'exe',*(process/'fd').iterdir()]:
                try:value=os.readlink(path)
                except FileNotFoundError:continue
                if value.startswith('/') and inside(Path(value.removesuffix(' (deleted)'))):
                    raise InstallRefused('材料仍有工作目录、程序或句柄消费者：'+process.name)
            if int(process.name) not in ancestors:
                for argument in (process/'cmdline').read_bytes().split(b'\0'):
                    if argument.startswith(b'/') and inside(Path(os.fsdecode(argument))):
                        raise InstallRefused('材料仍有外部命令消费者：'+process.name)
            after=(process/'stat').read_bytes()
            if before.split(b') ',1)[1].split()[19]!=after.split(b') ',1)[1].split()[19]:
                raise InstallRefused('消费者核对期间进程身份变化')
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError as error:raise InstallRefused('消费者不可核对：'+process.name) from error
