# SPDX-License-Identifier: GPL-3.0-or-later
"""将身份已核实的既有材料登记到原清单；未知材料只列出，不移动或删除。"""
import copy
import json
from pathlib import Path
import re
from nvenc_install import CATALOG, MATERIAL_ROOTS, InstallRefused, relative, safe, sha
from nvenc_autostart import AUTO_DROPIN, AUTO_STATE, ENV_FILE
from nvenc_runtime import DROPIN, STATE


def evidence_trees(installer,auto,evidence,digest):
    if evidence is None and digest is None:return {}
    if evidence is None or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):
        raise InstallRefused('迁移证据必须同时提供审阅后冻结的文件与 SHA256')
    path=installer.secure(evidence)
    if path.stat().st_size>2*1024*1024:raise InstallRefused('迁移证据超过读取上限')
    if installer.file_identity(path)['mode']!=0o600:raise InstallRefused('迁移证据须为受保护的 600 普通文件')
    with path.open('rb') as stream:data=stream.read(2*1024*1024+1)
    if len(data)>2*1024*1024 or sha(data)!=digest:raise InstallRefused('迁移证据超限或冻结摘要不符')
    value=json.loads(data)
    expected={'schema':1,'project':'Solis_FnOS_NVENC','boot':auto.host.info()['boot'],
              'current':installer.current(),
              'profile_sha256':sha(json.dumps(auto.p,sort_keys=True,separators=(',',':')).encode())}
    if not isinstance(value,dict) or set(value)!=set(expected)|{'trees'} or any(value[key]!=item for key,item in expected.items()):
        raise InstallRefused('迁移证据不属于当前合同、开机或安装版本')
    trees=value['trees']
    if not isinstance(trees,dict) or not trees:raise InstallRefused('迁移证据目录清单为空或未知')
    for name,tree in trees.items():
        if not isinstance(name,str):raise InstallRefused('迁移证据路径类型不符')
        path=safe(installer.root/name.lstrip('/'))
        if installer.tree_name(path)!=name or not name.startswith('/var/lib/solis-fnos-nvenc/'):
            raise InstallRefused('冻结证据仅限私有验收／升级包，不能绕过旧备份或暂存身份门')
        # 名称只限定可核对范围；完整成员和字节身份才决定是否登记。
        if not isinstance(tree,dict) or set(tree)!={'files','directories'} or not tree['files'] or not tree['directories']:
            raise InstallRefused('迁移证据结构不完整：'+name)
        for member in tree['files']:relative(member)
        for member in tree['directories']:
            if member!='.':relative(member)
        if installer.tree_inventory(path)!=tree:raise InstallRefused('迁移证据目录已改动或混入未知材料：'+name)
    return trees


def validate_catalog(installer,value):
    installer.owned_libraries()
    for name,expected in value['generated'].items():
        from nvenc_install import generated_location
        path=safe(installer.root/name.lstrip('/'))
        if generated_location(path)!=(installer.root,name):raise InstallRefused('原生成清单路径越界：'+name)
        if path.exists() and installer.file_identity(installer.secure(path))!={key:item for key,item in expected.items() if key!='parent_created'}:
            raise InstallRefused('原登记材料已改动，不重写身份：'+name)
    for name,expected in value['trees'].items():
        path=safe(installer.root/name.lstrip('/'))
        if installer.tree_name(path)!=name:raise InstallRefused('原目录清单越界')
        if path.exists() and installer.tree_inventory(path)!=expected:raise InstallRefused('原登记目录已改动：'+name)
    for name,expected in value['directories'].items():
        from nvenc_install import directory_location
        path=safe(installer.root/name.lstrip('/'))
        if directory_location(path)!=(installer.root,name):raise InstallRefused('原自建目录清单越界')
        if path.exists() and installer.directory_identity(path)!=expected:raise InstallRefused('原自建目录已改动：'+name)


def restored_state(auto,name):
    state=auto.state() if name==AUTO_STATE else auto.read_state()
    if not state:return False
    baseline=state.get('baseline')
    if not baseline:return False
    if name==STATE and state.get('library')!=auto.library:raise InstallRefused('恢复记录的候选路径不符：'+name)
    if set(baseline.get('protected',{}))!=set(auto.p['files']):raise InstallRefused('恢复记录组件不完整：'+name)
    for path,expected in auto.p['files'].items():
        if baseline['protected'][path]['sha256']!=expected:raise InstallRefused('恢复记录组件与固定合同不符：'+name)
    dependencies=baseline.get('dependencies')
    if dependencies is not None and dependencies.get('identities',{})!=auto.p['dependencies']:
        raise InstallRefused('恢复记录依赖不完整：'+name)
    # 服务启动保存的旧基线没有依赖字段；直接核对固定合同的实际文件，不补写旧记录。
    for path,expected in auto.p['dependencies'].items():
        if auto.identity(path)['sha256']!=expected:raise InstallRefused('当前恢复依赖与固定合同不符：'+path)
    if baseline.get('loaded_identity',{}).get('sha256')!=auto.p['allowed_baseline'].get(baseline.get('loaded')):
        raise InstallRefused('恢复记录的原库身份未知：'+name)
    if any(identity['sha256']!=auto.p['allowed_dropins'].get(path) for path,identity in baseline.get('dropins',{}).items()):
        raise InstallRefused('恢复记录含未知服务覆盖：'+name)
    return True


def remaining_materials(installer,value,tool_files,reasons):
    known=set(tool_files);directories=set()
    roots=[installer.root/name.lstrip('/') for name in MATERIAL_ROOTS]
    roots.extend(installer.root/name.lstrip('/') for name in value['directories'])
    for kind in ('files','generated'):
        known.update(installer.root/name.lstrip('/') for name in value[kind])
    for name,tree in value['trees'].items():
        folder=installer.root/name.lstrip('/')
        known.update(folder/relative(member) for member in tree['files'])
        directories.update(folder if member=='.' else folder/relative(member) for member in tree['directories'])
    for path in known:
        directories.update(parent for parent in path.parents if any(parent==root or root in parent.parents for root in roots))
    known.update(installer.root/name.lstrip('/') for name in (CATALOG,'/var/lib/solis-fnos-nvenc/.ownership.lock'))
    result=[]
    for root in roots:
        try:safe(root)
        except InstallRefused:
            result.append({'path':'/'+root.relative_to(installer.root).as_posix(),'reason':'路径含符号链接，保留；不读取目标'})
            continue
        if not root.exists() and not root.is_symlink():continue
        for path in (root,*sorted(root.rglob('*'))):
            name='/'+path.relative_to(installer.root).as_posix()
            if path.is_symlink():reason='符号链接，保留'
            elif path.is_dir():
                if path in directories or path in roots:continue
                reason='未登记目录，保留'
            elif path in known:continue
            else:reason='无独立身份依据，保留'
            reason=next((message for prefix,message in reasons.items() if name==prefix or name.startswith(prefix+'/')),reason)
            result.append({'path':name,'reason':reason})
    return result


def migration_plan(installer,auto,evidence,digest):
    value=installer.catalog();validate_catalog(installer,value)
    result=copy.deepcopy(value);accepted=[];reasons={}
    tool_files=installer.verified_tool_files(allow_legacy=True)
    def register(kind,name,identity):
        prior=result[kind].get(name)
        if prior is not None:
            comparison={key:item for key,item in prior.items() if key!='parent_created'}
            if comparison!=identity:raise InstallRefused('已有归属身份冲突，保留：'+name)
            return
        result[kind][name]=identity;accepted.append(name)
    library=safe(installer.root/auto.library.lstrip('/'))
    if library.exists():
        identity=installer.file_identity(installer.secure(library))
        if identity['sha256']!=auto.p['candidate_sha256'] or identity['mode']!=0o644:
            raise InstallRefused('libavcodec.so.62 与固定候选身份不符，保留')
        register('files',auto.library,identity)
    for name in (AUTO_STATE,STATE):
        path=safe(installer.root/name.lstrip('/'))
        if path.exists() and restored_state(auto,name):
            identity=installer.file_identity(installer.secure(path))
            if identity['mode']!=0o600:raise InstallRefused('恢复记录权限不符：'+name)
            register('generated',name,identity)
    env=safe(installer.root/ENV_FILE.lstrip('/'))
    if env.exists():
        identity=installer.file_identity(installer.secure(env))
        if env.read_bytes()!=b'' or identity['mode']!=0o600:raise InstallRefused('注入环境未清空或权限未知，保留')
        register('generated',ENV_FILE,identity)
    override=('[Service]\nEnvironment="LD_LIBRARY_PATH='+str(Path(auto.library).parent)+':'+auto.p['official_dir']+':/usr/trim/lib"\n').encode()
    retired='/var/lib/solis-fnos-nvenc/retired-'+sha(override)+'.conf'
    path=safe(installer.root/retired.lstrip('/'))
    if path.exists():
        identity=installer.file_identity(installer.secure(path))
        if path.read_bytes()!=override or identity['mode']!=0o600:raise InstallRefused('旧覆盖已改动，保留')
        register('generated',retired,identity)
    backups=safe(installer.root/'opt/solis-fnos-nvenc/backups')
    for path in sorted(backups.glob('legacy-*')) if backups.exists() else ():
        name='/'+path.relative_to(installer.root).as_posix()
        try:
            installer.tree_name(path);actual=installer.legacy_inventory(path)
            if path.name!='legacy-'+sha(json.dumps(actual,sort_keys=True).encode())[:16]:raise InstallRefused('旧备份与原指纹不符')
            identity=installer.tree_inventory(path)
        except (InstallRefused,OSError,ValueError) as error:
            reasons[name]=str(error)+'；保留';continue
        register('trees',name,identity)
    for name,tree in evidence_trees(installer,auto,evidence,digest).items():register('trees',name,tree)
    return result,accepted,remaining_materials(installer,result,tool_files,reasons),tool_files


def migrate_existing(installer,auto,verify_recovery,consumer_check,evidence=None,evidence_sha256=None):
    if installer.root!=auto.root:raise InstallRefused('迁移与恢复的目标根不一致')
    if auto.path(AUTO_DROPIN).exists() or auto.path(DROPIN).exists():raise InstallRefused('先暂停补丁并验证当前开机恢复')
    verify_recovery(auto)
    plan=migration_plan(installer,auto,evidence,evidence_sha256)
    value,accepted,remaining,_=plan
    if accepted:
        paths=[installer.root/name.lstrip('/') for name in accepted]
        consumer_check(paths)
        # 先完整核对，再一次写清单；变化或消费者失败不会部分收编。
        with installer.catalog_lock():
            verify_recovery(auto)
            if migration_plan(installer,auto,evidence,evidence_sha256)!=plan:
                raise InstallRefused('迁移核对期间身份发生变化，保留并停止')
            installer.save_catalog(value)
    return {'operation':'OWNERSHIP_MIGRATED','accepted':accepted,'remaining':remaining}
