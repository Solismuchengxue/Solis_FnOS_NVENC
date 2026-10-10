# SPDX-License-Identifier: GPL-3.0-or-later
"""Public-source, local Docker-only rebuild. Never authorizes a new candidate."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from urllib.request import urlopen
from urllib.parse import urlparse
import uuid

class BuildRefused(RuntimeError):
    pass

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def safe_path(path):
    path=Path(path).absolute()
    if '..' in path.parts or any(p.is_symlink() for p in (path,*path.parents)):
        raise BuildRefused('构建路径含符号链接或越界')
    return path

def fetch_sources(manifest, folder):
    folder=safe_path(folder);folder.mkdir(parents=True,exist_ok=True)
    for entry in manifest['files']:
        name=entry['name']
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+',name) or name in ('.','..'):
            raise BuildRefused('源码文件名越界')
        path=safe_path(folder/name)
        if path.exists():
            if not path.is_file() or path.stat().st_size!=entry['bytes'] or digest(path)!=entry['sha256']:
                raise BuildRefused('已有源码缓存身份不符，保留并停止：'+name)
            continue
        url=entry['url'];allowed={'ffmpeg.org','www.ffmpeg.org','codeload.github.com'}
        if urlparse(url).scheme!='https' or urlparse(url).hostname not in allowed:
            raise BuildRefused('不是批准的 HTTPS 源码来源')
        partial=folder/(name+'.part-'+uuid.uuid4().hex)
        print('下载并校验：'+name,flush=True)
        try:
            with urlopen(url,timeout=30) as response,partial.open('xb') as output:
                final=getattr(response,'geturl',lambda:url)()
                if urlparse(final).scheme!='https' or urlparse(final).hostname not in allowed:
                    raise BuildRefused('源码重定向越界')
                count=0
                while True:
                    chunk=response.read(65536)
                    if not chunk:break
                    count+=len(chunk)
                    if count>entry['bytes']:raise BuildRefused('源码超过固定大小：'+name)
                    output.write(chunk)
            if partial.stat().st_size!=entry['bytes'] or digest(partial)!=entry['sha256']:
                raise BuildRefused('源码大小或 SHA256 不符：'+name)
            # Exclusive destination creation; a concurrent invocation cannot replace it.
            with path.open('xb') as output,partial.open('rb') as source:
                shutil.copyfileobj(source,output)
            if digest(path)!=entry['sha256']:raise BuildRefused('源码写入校验失败')
            partial.unlink()
        except (OSError,ValueError) as error:
            raise BuildRefused('源码获取失败，保留本轮部分文件：'+name+': '+str(error)) from error
    return folder

def check_build_pair(first, second, expected, size):
    if any(Path(p).stat().st_size!=size or digest(p)!=expected for p in (first,second)):
        raise BuildRefused('双构建未匹配已验证候选；禁止安装或自动修改合同')
    return {'sha256':expected,'bytes':size,'clean_builds':2}

def build(project, work):
    if platform.system()!='Linux':raise BuildRefused('请在已有 Linux Docker 环境构建')
    project=safe_path(project);work=safe_path(work)
    if work.exists():raise BuildRefused('构建输出目录已存在，保留并停止')
    manifest=json.loads((project/'docs/build_sources.json').read_text())
    profile=json.loads((project/'docs/runtime_profile.json').read_text())
    if manifest['candidate_sha256']!=profile['candidate_sha256']:
        raise BuildRefused('构建合同与运行合同不一致')
    if digest(project/'docs/build_packages.txt')!=manifest['package_list_sha256']:
        raise BuildRefused('固定包清单身份不符')
    docker=['docker','--host','unix:///var/run/docker.sock']
    def call(args,log=None,timeout=1800):
        if log is None:
            result=subprocess.run(docker+args,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
            return result.stdout.strip()
        with log.open('xb') as output:
            subprocess.run(docker+args,check=True,stdout=output,stderr=subprocess.STDOUT,timeout=timeout)
    if call(['info','--format','{{.KernelVersion}}'],timeout=30)!=platform.release():
        raise BuildRefused('只接受当前主机的本地 Docker 引擎')
    work.mkdir(parents=True);sources=fetch_sources(manifest,work/'sources')
    environment=work/'environment';environment.mkdir()
    if shutil.disk_usage(work).free<8*1024**3:raise BuildRefused('需要至少 8 GiB 可用构建空间')
    token=uuid.uuid4().hex;name='solis-nvenc-prepare-'+token
    print('准备固定 Debian 依赖，仅在新容器内安装。',flush=True)
    call(['pull',manifest['base_image']],work/'base_pull.log')
    container=None
    try:
        container=call(['run','--detach','--name',name,'--label','solis.project=Solis_FnOS_NVENC','--label','solis.action='+token,
            '--cpus','2','--memory','4g','--pids-limit','256','--security-opt','no-new-privileges',
            '--mount',f'type=bind,source={project},target=/input,readonly',
            '--mount',f'type=bind,source={environment},target=/export',manifest['base_image'],'sleep','infinity'])
        call(['exec',container,'/bin/bash','/input/build/prepare_public_environment.sh',manifest['snapshot']],work/'prepare.log')
        image=call(['commit','--change','LABEL solis.project=Solis_FnOS_NVENC','--change','LABEL solis.environment=public-0.1.0',container])
        (work/'environment_image_id.txt').write_text(image+'\n')
    finally:
        if container:
            identity=json.loads(call(['inspect',container]))[0]
            if identity['Config']['Labels'].get('solis.action')!=token:raise BuildRefused('本轮容器身份变化，停止收尾')
            call(['rm','--force',container],timeout=30)
    for label in ('run1','run2'):
        output=work/label;output.mkdir()
        print('执行独立干净构建：'+label,flush=True)
        call(['run','--rm','--pull','never','--network','none','--cpus','2','--memory','4g','--pids-limit','256',
            '--cap-drop','ALL','--security-opt','no-new-privileges','--env','LC_ALL=C','--env','TZ=UTC','--env','SOURCE_DATE_EPOCH=0',
            '--label','solis.project=Solis_FnOS_NVENC','--label','solis.action='+token,
            '--mount',f'type=bind,source={project},target=/input,readonly',
            '--mount',f'type=bind,source={sources},target=/sources,readonly',
            '--mount',f'type=bind,source={output},target=/export',image,
            '/bin/bash','/input/build/run_public_build.sh'],work/(label+'.log'))
    result=check_build_pair(work/'run1/libavcodec.so.62',work/'run2/libavcodec.so.62',manifest['candidate_sha256'],manifest['candidate_bytes'])
    bundle=work/'bundle';bundle.mkdir();shutil.copyfile(work/'run1/libavcodec.so.62',bundle/'libavcodec.so.62')
    result.update({'license':'nonfree and unredistributable; local private only','profile':profile['id']})
    (bundle/'identity.json').write_text(json.dumps(result,indent=2)+'\n')
    (work/'build_result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('双构建与已验证候选身份一致；尚未安装或启用。',flush=True)
    return bundle

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('project');parser.add_argument('new_output');parser.add_argument('--sources-only',action='store_true')
    args=parser.parse_args()
    try:
        if args.sources_only:fetch_sources(json.loads((Path(args.project)/'docs/build_sources.json').read_text()),Path(args.new_output))
        else:build(args.project,args.new_output)
    except (BuildRefused,OSError,ValueError,subprocess.SubprocessError) as error:
        print('STOP：'+str(error));raise SystemExit(1)
