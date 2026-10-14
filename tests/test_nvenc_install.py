# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from nvenc_install import Installer, InstallRefused, inventory, atomic_json, sha

@unittest.skipUnless(sys.platform=='linux','Linux 文件权限合同')
class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'source';self.source.mkdir();(self.source/'script.py').write_text('print(1)\n')
        self.i=Installer(self.root,required_uid=self.source.stat().st_uid)
    def tearDown(self):self.temp.cleanup()
    def test_install_repeat_and_update_keep_previous(self):
        first=self.i.install(self.source,['script.py'],'0.1.0')
        self.assertEqual(self.i.current()['release'],first['release'])
    def test_reinstall_retained_version_switches_without_overwriting(self):
        first=self.i.install(self.source,['script.py'],'0.1.0')
        (self.source/'script.py').write_text('print(2)\n')
        second=self.i.install(self.source,['script.py'],'0.1.0');self.i.restore_previous()
        result=self.i.install(self.source,['script.py'],'0.1.0')
        self.assertEqual(result['release'],second['release'])
        self.assertEqual(json.loads((self.i.base/'previous.json').read_text())['release'],first['release'])
        self.assertFalse(any(p.name.startswith('.staging-') for p in self.i.base.iterdir()))
        self.assertEqual(self.i.install(self.source,['script.py'],'0.1.0')['operation'],'ALREADY_INSTALLED')
        (self.source/'script.py').write_text('print(2)\n')
        second=self.i.install(self.source,['script.py'],'0.1.0')
        self.assertNotEqual(first['release'],second['release'])
        self.assertTrue((self.i.base/'releases'/first['release']).is_dir())
        self.i.restore_previous()
        self.assertEqual(self.i.current()['release'],first['release'])
    def test_source_symlink_refused_before_creating_installation(self):
        (self.source/'link.py').symlink_to(self.source/'script.py')
        with self.assertRaises(InstallRefused):self.i.install(self.source,['link.py'],'0.1.0')
        self.assertFalse(self.i.base.exists())
    def test_unknown_existing_installation_preserved(self):
        self.i.base.mkdir(parents=True);(self.i.base/'user.txt').write_text('keep')
        with self.assertRaises(InstallRefused):self.i.install(self.source,['script.py'],'0.1.0')
        self.assertEqual((self.i.base/'user.txt').read_text(),'keep')
    def test_changed_managed_file_blocks_update_and_uninstall(self):
        current=self.i.install(self.source,['script.py'],'0.1.0')
        file=self.i.base/'releases'/current['release']/'script.py';file.write_text('changed')
        with self.assertRaises(InstallRefused):self.i.install(self.source,['script.py'],'0.1.0')
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertEqual(file.read_text(),'changed')
    def test_active_consumer_blocks_uninstall(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        def busy(roots):raise InstallRefused('consumer')
        with self.assertRaises(InstallRefused):self.i.uninstall(busy)
        self.assertIsNotNone(self.i.current())
    def test_unknown_recovery_material_blocks_before_tool_delete(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        state=self.root/'var/lib/solis-fnos-nvenc';state.mkdir(parents=True);(state/'evidence.json').write_text('{}')
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertTrue(self.i.base.exists());self.assertTrue((self.source/'script.py').is_file())
        self.assertTrue((state/'evidence.json').is_file())
    def test_pointer_escape_refused(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        path=self.i.base/'current.json';value=json.loads(path.read_text());value['release']='../../source';path.write_text(json.dumps(value))
        with self.assertRaises(InstallRefused):self.i.current()
    def test_unknown_extra_file_blocks_delete(self):
        current=self.i.install(self.source,['script.py'],'0.1.0')
        (self.i.base/'releases'/current['release']/'other.txt').write_text('keep')
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
    def test_failed_update_keeps_previous_bootstrap_readable(self):
        first=self.i.install(self.source,['script.py'],'0.1.0')
        (self.source/'script.py').write_text('print(2)\n')
        original=__import__('nvenc_install').atomic_json
        def disk_failure(path,value):
            if path.name=='manifest.json':raise OSError('disk failure')
            return original(path,value)
        with patch('nvenc_install.atomic_json',side_effect=disk_failure):
            with self.assertRaises(OSError):self.i.install(self.source,['script.py'],'0.1.0')
        self.assertEqual(self.i.current()['release'],first['release'])
        with self.assertRaises(InstallRefused):self.i.install(self.source,['script.py'],'0.1.0')
    def test_failed_legacy_registration_restores_original_entry(self):
        required={}
        for name in ('fnos-nvenc.sh','scripts/nvenc_runtime.py','docs/runtime_profile.json','artifacts/runtime_bundle/libavcodec.so.62'):
            file=self.i.base/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(name.encode())
            required[name]=sha(file.read_bytes())
        before=inventory(self.i.base)
        with patch('nvenc_install.LEGACY_REQUIRED',required),patch('nvenc_install.assert_no_consumers',return_value=None),patch.object(self.i,'record_tree',side_effect=OSError('registration failed')):
            with self.assertRaisesRegex(OSError,'registration failed'):self.i.adopt_legacy()
        self.assertTrue(self.i.base.is_dir())
        self.assertEqual(inventory(self.i.base),before)
        self.assertEqual(list((self.i.base.parent/'backups').iterdir()),[])
    def test_repair_can_restore_verified_previous_when_current_is_corrupt(self):
        first=self.i.install(self.source,['script.py'],'0.1.0')
        (self.source/'script.py').write_text('print(2)\n')
        second=self.i.install(self.source,['script.py'],'0.1.0')
        current_file=self.i.base/'releases'/second['release']/'script.py';current_file.write_text('corrupt')
        self.i.restore_previous()
        self.assertEqual(self.i.current()['release'],first['release'])
        self.assertEqual(current_file.read_text(),'corrupt')
    def test_unknown_library_blocks_before_any_owned_file_is_deleted(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        path='/opt/solis-fnos-nvenc/managed/'+('a'*64)+'/libavcodec.so.62'
        library=self.root/path.lstrip('/');library.parent.mkdir(parents=True);library.write_bytes(b'new')
        self.i.record_library(path)
        old=self.root/'opt/solis-fnos-nvenc/managed/history/libavcodec.so.62';old.parent.mkdir();old.write_bytes(b'keep')
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertTrue(library.exists());self.assertEqual(old.read_bytes(),b'keep')
    def test_changed_owned_library_stops_before_tool_delete(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        path='/opt/solis-fnos-nvenc/managed/'+('a'*64)+'/libavcodec.so.62'
        library=self.root/path.lstrip('/');library.parent.mkdir(parents=True);library.write_bytes(b'new')
        self.i.record_library(path);library.write_bytes(b'changed')
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertTrue(self.i.base.exists());self.assertEqual(library.read_bytes(),b'changed')

    def test_complete_uninstall_removes_owned_state_and_empty_project_directories(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        state=self.root/'var/lib/solis-fnos-nvenc/autostart.json'
        atomic_json(state,{'schema':1,'profile':'test','enabled':False,'phase':'restored'})
        self.i.uninstall(lambda roots:None)
        self.assertFalse((self.root/'opt/solis-fnos-nvenc').exists())
        self.assertFalse((self.root/'var/lib/solis-fnos-nvenc').exists())
        self.assertTrue((self.source/'script.py').is_file())

    def test_repeated_complete_uninstall_is_successful_without_a_candidate(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        self.i.uninstall(lambda roots:None)
        result=self.i.uninstall(lambda roots:None)
        self.assertEqual(result['operation'],'ALREADY_UNINSTALLED')
        self.assertEqual(result['remaining'],[])

    def test_enabled_or_unverified_recovery_state_blocks_uninstall(self):
        for value in ({'enabled':True,'phase':'loaded'},{'enabled':False,'phase':'config_disabled_unverified'},
                      {'enabled':False,'phase':'recovery_required'}):
            with self.subTest(value=value):
                if not self.i.base.exists():self.i.install(self.source,['script.py'],'0.1.0')
                state=self.root/'var/lib/solis-fnos-nvenc/autostart.json'
                atomic_json(state,{'schema':1,'profile':'test',**value})
                with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
                self.assertTrue(self.i.base.exists())

    def test_changed_owned_state_is_preserved_and_blocks_tool_delete(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        state=self.root/'var/lib/solis-fnos-nvenc/autostart.json'
        atomic_json(state,{'schema':1,'profile':'test','enabled':False,'phase':'restored'})
        state.write_text('changed')
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertTrue(self.i.base.exists());self.assertEqual(state.read_text(),'changed')

    def test_owned_install_input_is_removed_and_unknown_sibling_is_protected(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        folder=self.root/('vol1/1000/Solis_FnOS_NVENC/tmp/install-input-'+('a'*32))
        folder.mkdir(parents=True);(folder/'input.py').write_text('copy')
        self.i.record_tree(folder)
        other=folder.parent/'user.txt';other.write_text('keep')
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertTrue(folder.is_dir());self.assertTrue(self.i.base.is_dir())
        other.unlink()
        self.i.uninstall(lambda roots:None)
        self.assertFalse(folder.parent.exists());self.assertTrue(self.source.is_dir())

    @unittest.skipUnless(os.geteuid()==0,'需要真实不同 uid 的隔离目录')
    def test_user_owned_source_root_does_not_block_root_owned_install_input_cleanup(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        project=self.root/'vol1/1000/Solis_FnOS_NVENC';project.mkdir(parents=True)
        (project/'README.md').write_text('user source')
        os.chown(project,1000,1000);os.chown(project/'README.md',1000,1000)
        folder=project/('tmp/install-input-'+('d'*32));folder.mkdir(mode=0o700,parents=True)
        (folder/'input.py').write_text('copy');self.i.record_tree(folder)
        self.i.uninstall(lambda roots:None)
        self.assertFalse((project/'tmp').exists())
        self.assertEqual((project/'README.md').read_text(),'user source')

    def test_tree_changed_after_consumer_check_is_not_deleted(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        folder=self.root/('vol1/1000/Solis_FnOS_NVENC/tmp/install-input-'+('b'*32))
        folder.mkdir(parents=True);file=folder/'input.py';file.write_text('original')
        self.i.record_tree(folder)
        def changed(roots):file.write_text('changed')
        with self.assertRaises(InstallRefused):self.i.uninstall(changed)
        self.assertTrue(self.i.base.exists());self.assertEqual(file.read_text(),'changed')

    def test_tmp_replaced_at_directory_open_is_not_deleted(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        folder=self.root/('vol1/1000/Solis_FnOS_NVENC/tmp/install-input-'+('e'*32))
        folder.mkdir(parents=True);(folder/'input.py').write_text('original');self.i.record_tree(folder)
        temporary=folder.parent;backup=temporary.with_name('tmp-preserved');original_open=os.open
        def swapped(path,*args,**kwargs):
            if Path(path)==temporary and not backup.exists():
                temporary.rename(backup);shutil.copytree(backup,temporary)
                (folder/'input.py').write_text('user replacement')
            return original_open(path,*args,**kwargs)
        with patch('nvenc_install.os.open',side_effect=swapped):
            with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertTrue(self.i.base.is_dir())
        self.assertEqual((folder/'input.py').read_text(),'user replacement')
        self.assertEqual((backup/folder.name/'input.py').read_text(),'original')

    def test_catalog_cannot_authorize_a_path_outside_owned_roots(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        record=self.root/'var/lib/solis-fnos-nvenc/library_ownership.json'
        atomic_json(record,{'schema':1,'project':'Solis_FnOS_NVENC','files':{},
                            'generated':{'/source/script.py':{'sha256':'invalid','bytes':9}},'trees':{}})
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertTrue((self.source/'script.py').is_file());self.assertTrue(self.i.base.exists())

    def test_unknown_empty_directory_is_not_removed(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        folder=self.i.base.parent/'personal';folder.mkdir()
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertTrue(folder.is_dir());self.assertTrue(self.i.base.exists())

    def test_recorded_backup_tree_is_removed_after_restore(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        folder=self.i.base.parent/'backups'/('legacy-'+('c'*16))
        folder.mkdir(parents=True);(folder/'old.py').write_text('old')
        self.i.record_tree(folder)
        self.i.uninstall(lambda roots:None)
        self.assertFalse(self.i.base.parent.exists());self.assertTrue(self.source.is_dir())

    def test_uninstall_cli_does_not_require_bundle_or_leave_runtime_lock(self):
        from nvenc_cli import execute,parser
        from nvenc_autostart import AutoController
        self.i.install(self.source,['script.py'],'0.1.0')
        class Host:
            def hook_absent(self):pass
        def controller(root,bundle,profile,host,**kwargs):
            return AutoController(self.root,self.source/'missing',profile,host,**kwargs)
        with patch('nvenc_autostart.AutoController',side_effect=controller),patch('nvenc_autostart.ManagedHost',return_value=Host()),patch('nvenc_install.Installer',return_value=self.i),patch('nvenc_cli.choose_bundle',side_effect=RuntimeError('missing candidate')),patch('nvenc_cli.os.geteuid',return_value=0),patch('nvenc_install.assert_no_consumers',return_value=None):
            result=execute(parser().parse_args(['uninstall-tool']))
            self.assertEqual(result['operation'],'TOOL_UNINSTALLED')
            self.assertEqual(execute(parser().parse_args(['uninstall-tool']))['operation'],'ALREADY_UNINSTALLED')
        self.assertFalse((self.root/'run/lock/solis-nvenc-installer.lock').exists())
        self.assertFalse(self.i.base.parent.exists())

    def test_cli_uninstall_stops_when_service_has_not_really_restored(self):
        from nvenc_cli import execute,parser
        from nvenc_autostart import AutoController
        from nvenc_runtime import Refused
        profile={'id':'test','candidate_sha256':'a'*64,'official_dir':'/official'}
        (self.source/'metadata').mkdir()
        (self.source/'metadata/runtime_profile.json').write_text(json.dumps(profile))
        (self.source/'metadata/installer_status.json').write_text(json.dumps({'autostart_verified':True,'nas_installer_verified':True}))
        self.i.install(self.source,['script.py'],'0.1.0')
        boot=self.root/'proc/sys/kernel/random/boot_id';boot.parent.mkdir(parents=True);boot.write_text('boot-current')
        atomic_json(self.root/'var/lib/solis-fnos-nvenc/autostart.json',
                    {'schema':1,'profile':'test','enabled':False,'phase':'restored',
                     'baseline':{'boot':'boot-current','loaded':'/official/libavcodec.so.62',
                                 'environment':'LD_LIBRARY_PATH=/official','dropins':{}}})
        class Host:
            def hook_absent(self):pass
            def service(self):return {'active':True,'loaded':'/wrong/libavcodec.so.62','environment':'LD_LIBRARY_PATH=/official','dropins':[]}
        def controller(root,bundle,p,host,**kwargs):return AutoController(self.root,self.source,p,host,**kwargs)
        with patch('nvenc_cli.PROJECT',self.source),patch('nvenc_autostart.AutoController',side_effect=controller),patch('nvenc_autostart.ManagedHost',return_value=Host()),patch('nvenc_install.Installer',return_value=self.i),patch('nvenc_cli.choose_bundle',return_value=self.source),patch('nvenc_cli.os.geteuid',return_value=0),patch('nvenc_install.assert_no_consumers',return_value=None):
            with self.assertRaises(Refused):execute(parser().parse_args(['uninstall-tool']))
        self.assertTrue(self.i.base.is_dir())

if __name__=='__main__':unittest.main()
