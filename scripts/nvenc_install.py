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
import sys
from contextlib import contextmanager

CATALOG='/var/lib/solis-fnos-nvenc/library_ownership.json'
MATERIAL_ROOTS=('/opt/solis-fnos-nvenc','/var/lib/solis-fnos-nvenc',
                '/run/solis-fnos-nvenc','/vol1/1000/Solis_FnOS_NVENC/tmp')
LEGACY_REQUIRED={'fnos-nvenc.sh':'40384f2100e232354b94ea1cf8330ad2ce5c4201478db6f1d83f2965466859a2',
    'scripts/nvenc_runtime.py':'1250a7a648e9bc94709d250f11e11ee8b1447bdf3b70ff6356cb0762bd78f1cf',
    'docs/runtime_profile.json':'7500837c57ce9117b746ab6c0f12fa5d18151d4cb38420cf981462f699f7b559',
    'artifacts/runtime_bundle/libavcodec.so.62':'88e48674062ee5ef71864a2619324772bc856fec78c0d4793920fa7d4c15cd57'}

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

def _atomic_bytes(path,data):
    path=safe(path);created=not path.parent.exists();path.parent.mkdir(parents=True,exist_ok=True)
    if created:record_created_directory(path.parent)
    scratch=path.with_name(path.name+'.new-'+uuid.uuid4().hex)
    with scratch.open('xb') as stream:
        os.chmod(scratch,0o600);stream.write(data);stream.flush();os.fsync(stream.fileno())
    os.replace(scratch,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return created

def generated_location(path):
    text=safe(path).as_posix()
    for marker in ('/var/lib/solis-fnos-nvenc/','/run/solis-fnos-nvenc/',
                   '/etc/systemd/system/mediasrv.service.d/','/run/systemd/system/mediasrv.service.d/'):
        index=text.find(marker)
        if index<0:continue
        name=text[index:]
        if name in (CATALOG,'/var/lib/solis-fnos-nvenc/.ownership.lock'):return None
        if marker=='/run/solis-fnos-nvenc/' and name!=marker+'mediasrv.env':return None
        if marker.startswith('/etc/') and name!=marker+'96-solis-nvenc-autostart.conf':return None
        if marker.startswith('/run/systemd/') and name!=marker+'95-solis-nvenc-managed.conf':return None
        return Path(text[:index] or '/'),name
    return None

def atomic_bytes(path,data):
    created=_atomic_bytes(path,data)
    record_generated(path,parent_created=created)

def record_generated(path,parent_created=False):
    location=generated_location(path)
    if not location:return
    root,name=location;installer=Installer(root,required_uid=os.geteuid())
    # A bookkeeping failure must not block the original safe startup/restore path.
    # Missing or stale identities later block uninstall, rather than permit guesses.
    try:
        with installer.catalog_lock():
            value=installer.catalog();identity=installer.file_identity(path)
            if directory_location(Path(path).parent):
                identity['parent_created']=bool(parent_created or value['generated'].get(name,{}).get('parent_created'))
            value['generated'][name]=identity
            installer.save_catalog(value)
    except (InstallRefused,OSError,ValueError):
        print('材料归属登记失败；请保留材料，完整卸载将停止核对。',file=sys.stderr)

def directory_location(path):
    text=safe(path).as_posix()
    for name in ('/etc/systemd/system/mediasrv.service.d','/run/systemd/system/mediasrv.service.d'):
        if text.endswith(name):return Path(text[:-len(name)] or '/'),name
    return None

def record_created_directory(path):
    location=directory_location(path)
    if not location:return
    root,name=location;installer=Installer(root,required_uid=os.geteuid())
    try:
        with installer.catalog_lock():
            value=installer.catalog();value['directories'][name]=installer.directory_identity(path)
            installer.save_catalog(value)
    except (InstallRefused,OSError,ValueError):
        print('自建目录登记失败；请保留目录，核对后再清理。',file=sys.stderr)

def atomic_json(path,value):
    atomic_bytes(path,(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())

class Installer:
    def __init__(self,root=Path('/'),required_uid=0):
        self.root=safe(root);self.base=safe(self.root/'opt/solis-fnos-nvenc/tool');self.uid=required_uid

    def secure(self,path):
        path=safe(path)
        temporary=self.root/'vol1/1000/Solis_FnOS_NVENC/tmp'
        boundary=temporary if path==temporary or temporary in path.parents else self.root
        for item in (path,*path.parents):
            info=item.stat()
            if info.st_uid!=self.uid or stat.S_IMODE(info.st_mode)&0o022:
                raise InstallRefused('安装材料所有权或写权限不符：'+str(item))
            if item==boundary:break
        return path

    def directory_identity(self,path):
        info=self.secure(path).stat()
        if not stat.S_ISDIR(info.st_mode):raise InstallRefused('材料目录类型变化')
        return {'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),'device':info.st_dev,'inode':info.st_ino}

    def file_identity(self,path):
        path=safe(path);info=path.stat()
        if not stat.S_ISREG(info.st_mode):raise InstallRefused('材料不是普通文件：'+str(path))
        return {'sha256':sha(path.read_bytes()),'bytes':info.st_size,'uid':info.st_uid,
                'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}

    @contextmanager
    def catalog_lock(self):
        import fcntl
        folder=safe(self.root/'var/lib/solis-fnos-nvenc');folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.secure(folder);path=folder/'.ownership.lock'
        fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if info.st_uid!=self.uid or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size:
                raise InstallRefused('材料清单锁身份不符')
            try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as error:raise InstallRefused('另一材料登记正在进行') from error
            yield

    def catalog(self):
        path=safe(self.root/CATALOG.lstrip('/'))
        value=json.loads(self.secure(path).read_text()) if path.exists() else {'schema':1,'project':'Solis_FnOS_NVENC','files':{}}
        if not isinstance(value,dict) or value.get('schema')!=1 or value.get('project')!='Solis_FnOS_NVENC' or set(value)-{'schema','project','files','generated','trees','directories'}:
            raise InstallRefused('材料归属清单未知')
        for key in ('files','generated','trees','directories'):
            value.setdefault(key,{})
            if not isinstance(value[key],dict):raise InstallRefused('材料归属清单结构错误')
        return value

    def save_catalog(self,value):
        _atomic_bytes(self.root/CATALOG.lstrip('/'),(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())

    def tree_name(self,path):
        path=safe(path)
        try:name='/'+path.relative_to(self.root).as_posix()
        except ValueError as error:raise InstallRefused('材料目录越界') from error
        if not re.fullmatch(r'/vol1/1000/Solis_FnOS_NVENC/tmp/install-input-[a-f0-9]{32}|/opt/solis-fnos-nvenc/backups/legacy-[a-f0-9]{16}|/var/lib/solis-fnos-nvenc/(?:upgrade(?:-installer)?-[0-9]{8}-[a-f0-9]{10}|acceptance-v[0-9]{3}-[0-9]{8}-[a-f0-9-]{8,36})',name):
            raise InstallRefused('目录不属于安装器生成材料：'+name)
        return name

    def tree_inventory(self,path):
        path=self.secure(path)
        directories={}
        for item in (path,*path.rglob('*')):
            info=safe(item).stat()
            if info.st_uid!=self.uid or stat.S_IMODE(info.st_mode)&0o022:
                raise InstallRefused('生成材料权限或所有权变化：'+str(item))
            if item.is_dir():directories[item.relative_to(path).as_posix()]={'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}
        names=inventory(path)
        return {'files':{name:self.file_identity(path/relative(name)) for name in names},'directories':directories}

    def record_tree(self,path):
        name=self.tree_name(path);files=self.tree_inventory(path)
        with self.catalog_lock():
            value=self.catalog()
            if name in value['trees'] and value['trees'][name]!=files:raise InstallRefused('生成材料已改动，拒绝重新登记')
            value['trees'][name]=files;self.save_catalog(value)

    def record_library(self,absolute):
        if not re.fullmatch(r'/opt/solis-fnos-nvenc/managed/[a-f0-9]{64}/libavcodec\.so\.62',absolute):
            raise InstallRefused('库路径不属于安装器')
        path=self.secure(self.root/absolute.lstrip('/'));info=path.stat()
        identity={'sha256':sha(path.read_bytes()),'bytes':info.st_size,'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid}
        with self.catalog_lock():
            value=self.catalog()
            if absolute in value['files'] and value['files'][absolute]!=identity:raise InstallRefused('已记录的库身份漂移')
            value['files'][absolute]=identity;self.save_catalog(value)

    def owned_libraries(self):
        record=self.root/'var/lib/solis-fnos-nvenc/library_ownership.json'
        if not record.exists():return []
        value=self.catalog()
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
        unknown=[str(p) for p in self.base.iterdir() if p.name not in allowed and not p.name.startswith('.staging-')]
        if unknown:raise InstallRefused('工具根含未知材料，保留：'+', '.join(sorted(unknown)))

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
        if actual!=manifest['files']:
            names=sorted(name for name in set(actual)|set(manifest['files']) if actual.get(name)!=manifest['files'].get(name))
            raise InstallRefused('安装文件漂移或多出未知材料，保留：'+', '.join(str(directory/name) for name in names))
        for path in directory.rglob('*'):self.secure(path)
        if (self.base/'bootstrap.json').exists():
            expected=json.loads(self.secure(self.base/'bootstrap.json').read_text())
            if inventory(self.base,expected.keys())!=expected:raise InstallRefused('稳定启动入口身份不符')
            for name in expected:self.secure(self.base/name)
        return value

    def legacy_inventory(self,path):
        # 四项固定身份不变；两份旧说明由原备份指纹绑定，不用新版文档替代。
        required=LEGACY_REQUIRED
        actual=inventory(path)
        for name,expected in required.items():
            if actual.get(name,{}).get('sha256')!=expected:raise InstallRefused('已有工具身份未知，保留并停止：'+str(path/name))
        allowed=set(required)|{'docs/quick_start.md','docs/completion_report.md','artifacts/runtime_bundle/identity.json'}
        if set(actual)-allowed:raise InstallRefused('旧工具含未知材料，保留并停止：'+', '.join(str(path/name) for name in sorted(set(actual)-allowed)))
        directories={path}
        for name in actual:
            directories.update(p for p in (path/name).parents if p==path or path in p.parents)
        if any(p.is_dir() and p not in directories for p in path.rglob('*')):
            raise InstallRefused('旧工具含未知目录，保留并停止')
        for item in (path,*path.rglob('*')):self.secure(item)
        return actual

    def adopt_legacy(self):
        actual=self.legacy_inventory(self.base)
        assert_no_consumers([self.base])
        backup=safe(self.base.parent/'backups'/('legacy-'+sha(json.dumps(actual,sort_keys=True).encode())[:16]))
        if backup.exists():raise InstallRefused('旧工具备份位置已有材料')
        backup.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        os.rename(self.base,backup)
        try:self.record_tree(backup)
        except Exception:
            if self.base.exists():raise InstallRefused('旧工具登记失败且原入口被占用；保留备份并停止')
            os.rename(backup,self.base)
            raise
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

    def verified_tool_files(self,allow_legacy=False):
        files={}
        if allow_legacy and self.base.exists() and not (self.base/'owner.json').exists():
            names=self.legacy_inventory(self.base)
            return {self.base/relative(name):self.file_identity(self.base/name) for name in names}
        if self.base.exists():
            self.current();self.known_base(refuse_staging=True)
        releases=self.base/'releases'
        for path in releases.iterdir() if releases.exists() else ():
            if not path.is_dir() or path.is_symlink():raise InstallRefused('版本目录身份未知')
            manifest=json.loads(self.secure(path/'manifest.json').read_text())
            if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{16}',path.name) or manifest['release']!=path.name:
                raise InstallRefused('历史版本名称未知')
            fingerprint=sha(json.dumps({'version':manifest['version'],'files':manifest['files']},sort_keys=True).encode())[:16]
            if path.name!=manifest['version']+'-'+fingerprint:raise InstallRefused('历史清单与版本指纹不符')
            actual=inventory(path);actual.pop('manifest.json',None)
            if actual!=manifest['files']:raise InstallRefused('历史安装版本含漂移或未知材料')
            for item in path.rglob('*'):self.secure(item)
        for path in self.base.rglob('*') if self.base.exists() else ():
            if path.is_file():files[path]=self.file_identity(path)
        return files

    def removal_plan(self):
        files=self.verified_tool_files();roots=[safe(self.root/name.lstrip('/')) for name in MATERIAL_ROOTS]
        allowed_directories=set(roots)
        for path in self.owned_libraries():files[path]=self.file_identity(path)
        value=self.catalog()
        directories=set()
        for name,expected in value['directories'].items():
            path=safe(self.root/name.lstrip('/'))
            if directory_location(path)!=(self.root,name):raise InstallRefused('自建目录清单越界')
            if not path.exists():continue
            if self.directory_identity(path)!=expected or any(path.iterdir()):raise InstallRefused('自建启动目录已变化或非空，保留并停止：'+name)
            directories.add(path);roots.append(path)
        for name,expected in value['generated'].items():
            path=safe(self.root/name.lstrip('/'));location=generated_location(path)
            if not location or location!=(self.root,name):raise InstallRefused('生成文件清单越界：'+name)
            parent=directory_location(path.parent)
            if parent and expected.get('parent_created') and path.parent.exists() and parent[1] not in value['directories']:
                raise InstallRefused('自建启动目录缺少归属记录，保留并停止：'+parent[1])
            if not path.exists():continue
            self.secure(path)
            if self.file_identity(path)!={k:v for k,v in expected.items() if k!='parent_created'}:raise InstallRefused('生成文件已改动：'+name)
            if name.endswith(('96-solis-nvenc-autostart.conf','95-solis-nvenc-managed.conf')):
                raise InstallRefused('补丁配置尚未撤销，先恢复')
            if name=='/run/solis-fnos-nvenc/mediasrv.env' and path.read_bytes().strip():raise InstallRefused('注入环境尚未清空')
            if name in ('/var/lib/solis-fnos-nvenc/autostart.json','/var/lib/solis-fnos-nvenc/state.json'):
                state=json.loads(path.read_text())
                if state.get('enabled') or state.get('phase') not in ('prepared','restored','restored_after_failure','aborted_before_switch'):
                    raise InstallRefused('补丁未恢复或恢复未验证，保留状态')
            files[path]=self.file_identity(path)
        for name,expected in value['trees'].items():
            path=safe(self.root/name.lstrip('/'))
            if self.tree_name(path)!=name:raise InstallRefused('生成目录清单越界')
            if not path.exists():continue
            if self.tree_inventory(path)!=expected:raise InstallRefused('生成目录已改动：'+name)
            for relative_name,identity in expected['files'].items():
                file=safe(path/relative(relative_name));files[file]=identity
            for name in expected['directories']:
                allowed_directories.add(path if name=='.' else safe(path/relative(name)))
        record=safe(self.root/CATALOG.lstrip('/'))
        if record.exists():files[record]=self.file_identity(self.secure(record))
        lock=safe(record.parent/'.ownership.lock')
        if lock.exists():
            info=self.file_identity(self.secure(lock))
            if info['bytes'] or info['mode']!=0o600:raise InstallRefused('材料清单锁身份变化')
            files[lock]=info
        for path in files:
            for parent in path.parents:
                if any(parent==root or root in parent.parents for root in roots):allowed_directories.add(parent)
        for root in roots:
            if not root.exists():continue
            self.secure(root);directories.add(root)
            for path in root.rglob('*'):
                self.secure(path)
                if path.is_dir():
                    if path not in allowed_directories:raise InstallRefused('未登记目录，保留并停止：'+str(path))
                    directories.add(path)
                elif not path.is_file() or path not in files:raise InstallRefused('卸载未完成，未登记残留：'+str(path))
        return files,{path:self.directory_identity(path) for path in directories},roots

    def uninstall(self,consumer_check):
        existed=self.base.exists();files,directories,roots=self.removal_plan()
        consumer_check([*roots,*files])
        temporary=self.root/'vol1/1000/Solis_FnOS_NVENC/tmp'
        fd=os.open(temporary,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW) if temporary in directories else None
        try:
            if fd is not None:
                opened=os.fstat(fd);expected=directories[temporary]
                if (opened.st_dev,opened.st_ino)!=(expected['device'],expected['inode']):raise InstallRefused('暂存根在核对后被替换，停止卸载')
            if self.removal_plan()[:2]!=(files,directories):raise InstallRefused('消费者核对期间材料变化，停止卸载')
            # Anchor user-directory staging cleanup to the checked tmp inode.
            # A rename of its user-owned parent cannot redirect file deletion.
            for path in files:
                if temporary in path.parents:self.retire_temporary(fd,path.relative_to(temporary))
                else:path.unlink()
            for path in sorted(directories,key=lambda p:len(p.parts),reverse=True):
                if temporary in path.parents:self.retire_temporary(fd,path.relative_to(temporary),directory=True)
                elif path==temporary:
                    opened=os.fstat(fd);current=path.stat()
                    if (opened.st_dev,opened.st_ino)!=(current.st_dev,current.st_ino):raise InstallRefused('暂存根身份变化，卸载未完成')
                    path.rmdir()
                else:path.rmdir()
        finally:
            if fd is not None:os.close(fd)
        if any(path.exists() for path in roots) or any(path.exists() for path in files):raise InstallRefused('卸载后仍有残留，未完成')
        return {'operation':'TOOL_UNINSTALLED' if existed else 'ALREADY_UNINSTALLED','remaining':[],
                'source':'PRESERVED','recovery':'REMOVED_AFTER_RESTORE'}

    @staticmethod
    def retire_temporary(anchor,name,directory=False):
        parent=os.dup(anchor)
        try:
            for part in name.parts[:-1]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                os.close(parent);parent=child
            (os.rmdir if directory else os.unlink)(name.name,dir_fd=parent)
        finally:os.close(parent)

def assert_no_consumers(roots,own_fds=()):
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
                if int(process.name)==os.getpid() and path.parent==process/'fd' and path.name in {str(fd) for fd in own_fds}:continue
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
