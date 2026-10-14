# SPDX-License-Identifier: GPL-3.0-or-later
"""旧布局用真实临时文件；服务边界复用已有受控宿主。"""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_nvenc_runtime as runtime
from nvenc_install import Installer,InstallRefused,CATALOG
from nvenc_autostart import AutoController
from nvenc_cli import verify_tool_recovery
try:
    from nvenc_migrate import migrate_existing
except ImportError:
    migrate_existing=None

def digest(data):return hashlib.sha256(data).hexdigest()
def json_bytes(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()

@unittest.skipUnless(sys.platform=='linux','Linux 旧布局迁移')
class MigrationTests(unittest.TestCase):
    def setUp(self):
        runtime.RuntimeTests.setUp(self)
        self.i=Installer(self.root,required_uid=self.root.stat().st_uid)
        self.i.install(self.bundle,['libavcodec.so.62'],'0.1.1')
        self.boot=self.root/'proc/sys/kernel/random/boot_id';self.boot.parent.mkdir(parents=True);self.boot.write_text(self.host.boot)
        self.library=self.root/self.c.library.lstrip('/');self.write(self.library,b'private candidate',0o644)
        state={'schema':1,'profile':self.profile['id'],'phase':'restored','baseline':self.c.snapshot(),
               'library':self.c.library,'dropin_sha256':digest(self.dropin())}
        self.write(self.root/'var/lib/solis-fnos-nvenc/state.json',json_bytes(state))
        self.auto=AutoController(self.root,self.bundle,self.profile,self.host,verified=True)
        self.catalog=self.root/CATALOG.lstrip('/')
    def tearDown(self):self.temp.cleanup()
    def write(self,path,data,mode=0o600):
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(data);os.chmod(path,mode)
    def dropin(self):
        return ('[Service]\nEnvironment="LD_LIBRARY_PATH='+str(Path(self.c.library).parent)+':/official:/usr/trim/lib"\n').encode()
    def migrate(self,evidence=None,evidence_sha256=None,consumer=None):
        self.assertIsNotNone(migrate_existing,'缺少既有安装的精确归属迁移')
        return migrate_existing(self.i,self.auto,verify_tool_recovery,consumer or (lambda roots:None),evidence,evidence_sha256)
    def receipt(self):
        folder=self.root/'var/lib/solis-fnos-nvenc/upgrade-installer-20300101-aaaaaaaaaa'
        self.write(folder/'proof.json',b'known recovery material\n')
        info=(folder/'proof.json').stat();directory=folder.stat()
        identity={'sha256':digest(b'known recovery material\n'),'bytes':len(b'known recovery material\n'),'uid':info.st_uid,'gid':info.st_gid,'mode':0o600}
        value={'schema':1,'project':'Solis_FnOS_NVENC','boot':self.host.boot,'current':self.i.current(),
               'profile_sha256':digest(json.dumps(self.profile,sort_keys=True,separators=(',',':')).encode()),
               'trees':{'/'+folder.relative_to(self.root).as_posix():{'files':{'proof.json':identity},
                         'directories':{'.':{'uid':directory.st_uid,'gid':directory.st_gid,'mode':0o700}}}}}
        evidence=self.root/'reviewed-evidence.json';self.write(evidence,json_bytes(value))
        return folder,evidence,value
    def update_cli(self):
        import nvenc_cli
        source=self.root/'source';public=Path(__file__).resolve().parents[1]
        for name in nvenc_cli.payload_files(public):self.write(source/name,(public/name).read_bytes())
        self.write(source/'metadata/runtime_profile.json',json_bytes(self.profile))
        self.write(self.bundle/'identity.json',json_bytes({'sha256':self.profile['candidate_sha256']}))
        with patch('nvenc_cli.PROJECT',source),patch('nvenc_cli.DATA',self.root/'vol1/1000/Solis_FnOS_NVENC'), \
             patch('nvenc_runtime.Controller',return_value=self.c),patch('nvenc_autostart.AutoController',return_value=self.auto), \
             patch('nvenc_autostart.ManagedHost',return_value=self.host),patch('nvenc_cli.choose_bundle',return_value=self.bundle), \
             patch('nvenc_install.Installer',return_value=self.i),patch('nvenc_install.assert_no_consumers'), \
             patch('nvenc_cli.os.geteuid',return_value=0):
            return nvenc_cli.execute(nvenc_cli.parser().parse_args(['update-tool']))
    def test_missing_catalog_recovers_existing_library_and_restored_state(self):
        before=self.library.read_bytes();state=(self.root/'var/lib/solis-fnos-nvenc/state.json').read_bytes()
        result=self.migrate()
        self.assertIn(self.c.library,result['accepted'])
        self.assertIn('/var/lib/solis-fnos-nvenc/state.json',result['accepted'])
        self.assertEqual(self.i.catalog()['files'][self.c.library]['sha256'],digest(b'private candidate'))
        self.assertEqual(self.library.read_bytes(),before)
        self.assertEqual((self.root/'var/lib/solis-fnos-nvenc/state.json').read_bytes(),state)
        self.assertEqual(self.host.restarts,0)
    def test_unknown_material_is_retained_and_listed_and_blocks_uninstall(self):
        unknown=self.root/'var/lib/solis-fnos-nvenc/user-note.txt';self.write(unknown,b'keep')
        result=self.migrate()
        self.assertIn('/var/lib/solis-fnos-nvenc/user-note.txt',{x['path'] for x in result['remaining']})
        self.assertNotIn('/var/lib/solis-fnos-nvenc/user-note.txt',self.i.catalog()['generated'])
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertEqual(unknown.read_bytes(),b'keep');self.assertTrue(self.i.base.exists())
    def test_real_autostart_restored_record_has_no_legacy_library_field(self):
        state={'schema':1,'profile':self.profile['id'],'enabled':False,'phase':'restored',
               'baseline':self.c.snapshot(),'startup':'PREPARED','transaction':'a'*32}
        self.write(self.root/'var/lib/solis-fnos-nvenc/autostart.json',json_bytes(state))
        result=self.migrate()
        self.assertIn('/var/lib/solis-fnos-nvenc/autostart.json',result['accepted'])
        self.assertEqual(self.host.restarts,0)
    def test_incomplete_restored_record_does_not_create_catalog(self):
        path=self.root/'var/lib/solis-fnos-nvenc/state.json'
        state=json.loads(path.read_text());state['baseline']['protected'].pop('/official/mediasrv')
        self.write(path,json_bytes(state))
        with self.assertRaises(InstallRefused):self.migrate()
        self.assertFalse(self.catalog.exists())
    def test_real_enable_disable_then_migrate_and_uninstall(self):
        from test_nvenc_autostart import AutoTests
        fixture=AutoTests();fixture.setUp()
        try:
            installer=Installer(fixture.root,required_uid=fixture.root.stat().st_uid)
            installer.install(fixture.bundle,['libavcodec.so.62'],'0.1.1')
            boot=fixture.root/'proc/sys/kernel/random/boot_id';boot.parent.mkdir(parents=True);boot.write_text(fixture.host.boot)
            fixture.c.enable()
            fixture.host.boot='new-boot';boot.write_text(fixture.host.boot)
            fixture.host.env='LD_LIBRARY_PATH=/official';fixture.host.loaded=None
            self.assertEqual(fixture.c.boot_prepare()['startup'],'PREPARED')
            fixture.c.disable()
            self.assertNotIn('library',fixture.c.state())
            self.assertNotIn('dependencies',fixture.c.state()['baseline'])
            restarts=fixture.host.restarts
            migrate_existing(installer,fixture.c,verify_tool_recovery,lambda roots:None)
            installer.uninstall(lambda roots:None)
            self.assertFalse(installer.base.exists());self.assertEqual(fixture.host.restarts,restarts)
        finally:fixture.tearDown()
    def test_boot_baseline_without_old_dependency_field_checks_actual_files(self):
        dependency=self.root/'official/dep.so';self.write(dependency,b'fixed dependency')
        baseline=self.c.snapshot();baseline.pop('dependencies')
        self.profile['dependencies']={'/official/dep.so':digest(dependency.read_bytes())}
        (self.root/'var/lib/solis-fnos-nvenc/state.json').unlink()
        state={'schema':1,'profile':self.profile['id'],'enabled':False,'phase':'restored','baseline':baseline}
        self.write(self.root/'var/lib/solis-fnos-nvenc/autostart.json',json_bytes(state))
        self.migrate();original=self.catalog.read_bytes();dependency.write_bytes(b'changed')
        with self.assertRaises(InstallRefused):self.migrate()
        self.assertEqual(self.catalog.read_bytes(),original)
    def test_reviewed_receipt_cannot_bypass_fixed_legacy_backup_gate(self):
        _,evidence,value=self.receipt()
        folder=self.root/'opt/solis-fnos-nvenc/backups/legacy-aaaaaaaaaaaaaaaa'
        self.write(folder/'user.txt',b'keep')
        value['trees']={'/'+folder.relative_to(self.root).as_posix():self.i.tree_inventory(folder)}
        self.write(evidence,json_bytes(value))
        with self.assertRaises(InstallRefused):self.migrate(evidence,digest(evidence.read_bytes()))
        self.assertFalse(self.catalog.exists());self.assertEqual((folder/'user.txt').read_bytes(),b'keep')
    def test_unknown_member_of_registered_startup_directory_is_listed(self):
        directory=self.root/'etc/systemd/system/mediasrv.service.d';directory.mkdir(mode=0o700)
        value=self.i.catalog();name='/etc/systemd/system/mediasrv.service.d'
        value['directories'][name]=self.i.directory_identity(directory);self.i.save_catalog(value)
        self.write(directory/'user-note.txt',b'keep')
        result=self.migrate()
        self.assertIn(name+'/user-note.txt',{x['path'] for x in result['remaining']})
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertEqual((directory/'user-note.txt').read_bytes(),b'keep')
    def test_unregistered_tmp_symlink_does_not_scan_its_target(self):
        outside=self.root/'outside';self.write(outside/'private.txt',b'outside scope')
        temporary=self.root/'vol1/1000/Solis_FnOS_NVENC/tmp';temporary.parent.mkdir(parents=True)
        temporary.symlink_to(outside,target_is_directory=True)
        result=self.migrate()
        paths={item['path'] for item in result['remaining']}
        self.assertIn('/vol1/1000/Solis_FnOS_NVENC/tmp',paths)
        self.assertFalse(any('private.txt' in path for path in paths))
        self.assertEqual((outside/'private.txt').read_bytes(),b'outside scope')
    def test_update_cli_migrates_before_switch_with_complete_public_payload(self):
        import nvenc_cli
        public=Path(__file__).resolve().parents[1];result=self.update_cli()
        self.assertIn(self.c.library,result['migration']['accepted'])
        self.assertEqual(self.host.restarts,0)
        release=self.i.base/'releases'/result['release']
        manifest=json.loads((release/'manifest.json').read_text())
        self.assertEqual(len(manifest['files']),len(nvenc_cli.payload_files(public))+2)
        self.assertEqual((release/'scripts/nvenc_migrate.py').read_bytes(),(public/'scripts/nvenc_migrate.py').read_bytes())
        self.assertTrue((self.i.base/'previous.json').is_file())
    def test_update_cli_still_accepts_known_ownerless_legacy_layout(self):
        os.rename(self.i.base,self.root/'retained-test-tool')
        names=('fnos-nvenc.sh','scripts/nvenc_runtime.py','docs/runtime_profile.json','artifacts/runtime_bundle/libavcodec.so.62',
               'docs/completion_report.md','docs/quick_start.md')
        data={name:('old '+name).encode() for name in names}
        for name,raw in data.items():self.write(self.i.base/name,raw)
        with patch('nvenc_install.LEGACY_REQUIRED',{name:digest(data[name]) for name in names[:4]}):result=self.update_cli()
        backup=Path(result['legacy_backup'])
        self.assertEqual((backup/'docs/completion_report.md').read_bytes(),data['docs/completion_report.md'])
        self.assertEqual(len(self.i.catalog()['trees']['/'+backup.relative_to(self.root).as_posix()]['files']),6)
        self.assertEqual(self.i.current()['release'],result['release']);self.assertEqual(self.host.restarts,0)
    def test_changed_candidate_is_not_rebaselined(self):
        self.library.write_bytes(b'changed')
        with self.assertRaisesRegex(InstallRefused,'libavcodec'):self.migrate()
        self.assertFalse(self.catalog.exists());self.assertEqual(self.library.read_bytes(),b'changed')
    def test_unknown_tool_file_is_named_and_kept_before_catalog_write(self):
        unknown=self.i.base/'user-note.txt';self.write(unknown,b'keep')
        with self.assertRaisesRegex(InstallRefused,'user-note.txt'):self.migrate()
        self.assertFalse(self.catalog.exists());self.assertEqual(unknown.read_bytes(),b'keep')
    def test_old_boot_is_not_accepted(self):
        self.boot.write_text('another-boot')
        with self.assertRaises(RuntimeError):self.migrate()
        self.assertFalse(self.catalog.exists())
    def test_active_service_consumer_stops_before_registration(self):
        def busy(roots):raise InstallRefused('仍有消费者')
        with self.assertRaises(InstallRefused):self.migrate(consumer=busy)
        self.assertFalse(self.catalog.exists());self.assertTrue(self.library.exists())
    def test_frozen_evidence_tree_and_repeat_migration_preserve_record(self):
        folder,evidence,_=self.receipt()
        result=self.migrate(evidence,digest(evidence.read_bytes()))
        name='/'+folder.relative_to(self.root).as_posix()
        self.assertIn(name,result['accepted']);before=self.catalog.read_bytes()
        self.migrate(evidence,digest(evidence.read_bytes()))
        self.assertEqual(self.catalog.read_bytes(),before)
        self.assertTrue((folder/'proof.json').exists())
    def test_evidence_file_change_refused_without_catalog_write(self):
        folder,evidence,_=self.receipt();frozen=digest(evidence.read_bytes())
        evidence.write_bytes(evidence.read_bytes()+b' ')
        with self.assertRaises(InstallRefused):self.migrate(evidence,frozen)
        self.assertFalse(self.catalog.exists());self.assertTrue((folder/'proof.json').exists())
    def test_changed_evidence_member_not_rebaselined(self):
        folder,evidence,_=self.receipt();(folder/'proof.json').write_bytes(b'changed')
        with self.assertRaises(InstallRefused):self.migrate(evidence,digest(evidence.read_bytes()))
        self.assertFalse(self.catalog.exists());self.assertEqual((folder/'proof.json').read_bytes(),b'changed')
    def test_added_unknown_evidence_member_stops_whole_tree(self):
        folder,evidence,_=self.receipt();self.write(folder/'user.txt',b'keep')
        with self.assertRaises(InstallRefused):self.migrate(evidence,digest(evidence.read_bytes()))
        self.assertFalse(self.catalog.exists());self.assertTrue((folder/'user.txt').exists())
    def test_evidence_escape_and_wrong_profile_are_refused(self):
        folder,evidence,value=self.receipt()
        for change in ('escape','profile','pointer','boot'):
            with self.subTest(change=change):
                altered=json.loads(json.dumps(value))
                if change=='escape':altered['trees']['/source']=altered['trees'].pop(next(iter(altered['trees'])))
                if change=='profile':altered['profile_sha256']='f'*64
                if change=='pointer':altered['current']['manifest_sha256']='f'*64
                if change=='boot':altered['boot']='different'
                self.write(evidence,json_bytes(altered))
                with self.assertRaises(InstallRefused):self.migrate(evidence,digest(evidence.read_bytes()))
                self.assertFalse(self.catalog.exists())
    def test_evidence_requires_separate_frozen_digest(self):
        _,evidence,_=self.receipt()
        with self.assertRaises(InstallRefused):self.migrate(evidence,None)
        self.assertFalse(self.catalog.exists())
    def test_symlink_in_evidence_tree_is_preserved_and_refused(self):
        folder,evidence,_=self.receipt();(folder/'proof.json').unlink();(folder/'proof.json').symlink_to(self.root/'official/mediasrv')
        with self.assertRaises(InstallRefused):self.migrate(evidence,digest(evidence.read_bytes()))
        self.assertTrue((folder/'proof.json').is_symlink());self.assertFalse(self.catalog.exists())
    def test_material_changed_during_consumer_check_stops_registration(self):
        def changed(roots):self.library.write_bytes(b'changed during check')
        with self.assertRaises(InstallRefused):self.migrate(consumer=changed)
        self.assertFalse(self.catalog.exists());self.assertTrue(self.i.base.exists())
    def test_known_retired_override_is_migrated_and_clean_uninstall_keeps_source(self):
        retired=self.root/'var/lib/solis-fnos-nvenc'/('retired-'+digest(self.dropin())+'.conf')
        self.write(retired,self.dropin());self.migrate()
        self.i.uninstall(lambda roots:None)
        self.assertFalse((self.root/'opt/solis-fnos-nvenc').exists())
        self.assertFalse((self.root/'var/lib/solis-fnos-nvenc').exists())
        self.assertEqual((self.bundle/'libavcodec.so.62').read_bytes(),b'private candidate')
    def test_original_six_file_backup_uses_its_fingerprint_not_public_doc_bytes(self):
        names=('fnos-nvenc.sh','scripts/nvenc_runtime.py','docs/runtime_profile.json','artifacts/runtime_bundle/libavcodec.so.62',
               'docs/completion_report.md','docs/quick_start.md')
        data={name:('old '+name).encode() for name in names}
        fingerprint=digest(json.dumps({name:{'sha256':digest(raw),'bytes':len(raw)} for name,raw in data.items()},sort_keys=True).encode())[:16]
        folder=self.root/'opt/solis-fnos-nvenc/backups'/('legacy-'+fingerprint)
        for name,raw in data.items():self.write(folder/name,raw)
        core={name:digest(data[name]) for name in names[:4]}
        with patch('nvenc_install.LEGACY_REQUIRED',core):result=self.migrate()
        self.assertIn('/'+folder.relative_to(self.root).as_posix(),result['accepted'])
        self.assertEqual(len(self.i.catalog()['trees']['/'+folder.relative_to(self.root).as_posix()]['files']),6)
    def test_backup_changed_from_its_named_fingerprint_is_retained(self):
        folder=self.root/'opt/solis-fnos-nvenc/backups/legacy-aaaaaaaaaaaaaaaa'
        self.write(folder/'user.txt',b'keep')
        result=self.migrate()
        self.assertNotIn('/'+folder.relative_to(self.root).as_posix(),result['accepted'])
        self.assertTrue(any(x['path'].startswith('/opt/solis-fnos-nvenc/backups/') for x in result['remaining']))
        self.assertEqual((folder/'user.txt').read_bytes(),b'keep')

if __name__=='__main__':unittest.main()
