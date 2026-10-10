# SPDX-License-Identifier: GPL-3.0-or-later
"""Stable dispatcher: verify a version before importing or executing its code."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import uuid

def licensed(text):
    values=re.findall(r'^\s*License Status\s*:\s*([^\n]+)',text,re.M)
    return len(values)==1 and values[0].strip().split(' (',1)[0]=='Licensed'

def prepare_startup(base,root=Path('/'),uid=0):
    """Minimal stable fallback: no candidate code runs until stale injection is cleared."""
    root=Path(root);path=root/'run/solis-fnos-nvenc/mediasrv.env'
    for item in (path,*path.parents):
        if item.is_symlink():raise RuntimeError('启动环境路径含符号链接，禁止继续')
        if item==root:break
        if item.exists():
            info=item.stat()
            if info.st_uid!=uid or (stat.S_IMODE(info.st_mode)&0o022 and not stat.S_IMODE(info.st_mode)&stat.S_ISVTX):
                raise RuntimeError('启动环境所有权或权限未知，禁止继续')
    if path.exists() and (not path.is_file() or stat.S_IMODE(path.stat().st_mode)!=0o600):
        raise RuntimeError('启动环境文件身份未知，禁止继续')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    scratch=path.with_name(path.name+'.empty-'+uuid.uuid4().hex)
    with scratch.open('xb') as stream:os.chmod(scratch,0o600);stream.flush();os.fsync(stream.fileno())
    os.replace(scratch,path)
    try:return {'startup':'VALIDATED','release':resolve_release(base,uid)}
    except (RuntimeError,OSError,ValueError,KeyError) as error:
        return {'startup':'SKIPPED','reason':str(error)}

def resolve_release(base,uid=0):
    base=Path(base).absolute()
    def checked(path):
        if '..' in path.parts or any(p.is_symlink() for p in (path,*path.parents)):
            raise RuntimeError('稳定入口路径越界或含符号链接')
        info=path.stat()
        if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):raise RuntimeError('稳定入口含特殊文件')
        if info.st_uid!=uid or stat.S_IMODE(info.st_mode)&0o022:raise RuntimeError('稳定入口所有权或权限不符')
        return path
    checked(base)
    if json.loads(checked(base/'owner.json').read_text())!={'project':'Solis_FnOS_NVENC','schema':1}:
        raise RuntimeError('稳定入口项目身份不符')
    pointer=json.loads(checked(base/'current.json').read_text());name=pointer['release']
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{16}',name):raise RuntimeError('版本指针不合法')
    directory=checked(base/'releases'/name);manifest_path=checked(directory/'manifest.json');raw=manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pointer['manifest_sha256']:raise RuntimeError('版本清单 SHA256 不符')
    manifest=json.loads(raw)
    if manifest['release']!=name:raise RuntimeError('版本清单名称不符')
    actual={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual!=set(manifest['files'])|{'manifest.json'}:raise RuntimeError('版本含未知文件或缺失材料')
    for path in directory.rglob('*'):checked(path)
    for relative,expected in manifest['files'].items():
        part=PurePosixPath(relative)
        if part.is_absolute() or '..' in part.parts or '\\' in relative:raise RuntimeError('版本文件清单越界')
        data=checked(directory/part).read_bytes()
        if len(data)!=expected['bytes'] or hashlib.sha256(data).hexdigest()!=expected['sha256']:
            raise RuntimeError('版本文件身份不符：'+relative)
    return directory

if __name__=='__main__':
    try:
        if os.geteuid()!=0:raise RuntimeError('安装入口需要 sudo')
        if len(sys.argv)>1 and sys.argv[1]=='boot-prepare':
            result=prepare_startup(Path(__file__).absolute().parent)
            if result['startup']=='SKIPPED':
                print(json.dumps(result,ensure_ascii=False));sys.exit(0)
        release=resolve_release(Path(__file__).absolute().parent)
        os.environ.pop('LD_LIBRARY_PATH',None)
        os.execv('/usr/bin/python3',['python3','-B',str(release/'scripts/nvenc_cli.py'),*sys.argv[1:]])
    except (RuntimeError,OSError,ValueError,KeyError) as error:
        print('STOP：'+str(error),file=sys.stderr);sys.exit(1)
