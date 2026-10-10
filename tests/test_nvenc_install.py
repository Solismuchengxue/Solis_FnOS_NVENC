# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from nvenc_install import Installer, InstallRefused, inventory

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
    def test_uninstall_preserves_source_and_recovery_directory(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        state=self.root/'var/lib/solis-fnos-nvenc';state.mkdir(parents=True);(state/'evidence.json').write_text('{}')
        self.i.uninstall(lambda roots:None)
        self.assertFalse(self.i.base.exists());self.assertTrue((self.source/'script.py').is_file())
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
    def test_repair_can_restore_verified_previous_when_current_is_corrupt(self):
        first=self.i.install(self.source,['script.py'],'0.1.0')
        (self.source/'script.py').write_text('print(2)\n')
        second=self.i.install(self.source,['script.py'],'0.1.0')
        current_file=self.i.base/'releases'/second['release']/'script.py';current_file.write_text('corrupt')
        self.i.restore_previous()
        self.assertEqual(self.i.current()['release'],first['release'])
        self.assertEqual(current_file.read_text(),'corrupt')
    def test_uninstall_only_removes_newly_owned_library(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        path='/opt/solis-fnos-nvenc/managed/'+('a'*64)+'/libavcodec.so.62'
        library=self.root/path.lstrip('/');library.parent.mkdir(parents=True);library.write_bytes(b'new')
        self.i.record_library(path)
        old=self.root/'opt/solis-fnos-nvenc/managed/history/libavcodec.so.62';old.parent.mkdir();old.write_bytes(b'keep')
        self.i.uninstall(lambda roots:None)
        self.assertFalse(library.exists());self.assertEqual(old.read_bytes(),b'keep')
    def test_changed_owned_library_stops_before_tool_delete(self):
        self.i.install(self.source,['script.py'],'0.1.0')
        path='/opt/solis-fnos-nvenc/managed/'+('a'*64)+'/libavcodec.so.62'
        library=self.root/path.lstrip('/');library.parent.mkdir(parents=True);library.write_bytes(b'new')
        self.i.record_library(path);library.write_bytes(b'changed')
        with self.assertRaises(InstallRefused):self.i.uninstall(lambda roots:None)
        self.assertTrue(self.i.base.exists());self.assertEqual(library.read_bytes(),b'changed')

if __name__=='__main__':unittest.main()
