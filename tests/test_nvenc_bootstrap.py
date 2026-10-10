# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
import tempfile
import os
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from nvenc_bootstrap import resolve_release, prepare_startup
from nvenc_install import Installer

@unittest.skipUnless(sys.platform=='linux','Linux 权限与符号链接')
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'source';self.source.mkdir();(self.source/'script.py').write_text('print(1)\n')
        self.i=Installer(self.root,required_uid=self.source.stat().st_uid);self.i.install(self.source,['script.py'],'0.1.0')
    def tearDown(self):self.temp.cleanup()
    def test_verified_pointer_selects_complete_version(self):
        result=resolve_release(self.i.base,self.source.stat().st_uid)
        self.assertEqual((result/'script.py').read_text(),'print(1)\n')
    def test_changed_version_never_executes(self):
        release=self.i.current()['release'];(self.i.base/'releases'/release/'script.py').write_text('evil')
        with self.assertRaises(RuntimeError):resolve_release(self.i.base,self.source.stat().st_uid)
    def test_linked_pointer_refused(self):
        pointer=self.i.base/'current.json';data=pointer.read_bytes();pointer.unlink()
        other=self.root/'other';other.write_bytes(data);pointer.symlink_to(other)
        with self.assertRaises(RuntimeError):resolve_release(self.i.base,self.source.stat().st_uid)
    def test_corrupt_release_boot_falls_back_with_empty_environment(self):
        release=self.i.current()['release'];(self.i.base/'releases'/release/'script.py').write_text('corrupt')
        env=self.root/'run/solis-fnos-nvenc/mediasrv.env';env.parent.mkdir(parents=True,mode=0o700)
        env.write_text('LD_LIBRARY_PATH=/old\n');env.chmod(0o600)
        result=prepare_startup(self.i.base,self.root,self.source.stat().st_uid)
        self.assertEqual(result['startup'],'SKIPPED');self.assertEqual(env.read_bytes(),b'')
    def test_unknown_special_file_stops_dispatch(self):
        release=self.i.current()['release'];os.mkfifo(self.i.base/'releases'/release/'unknown.pipe',0o600)
        with self.assertRaises(RuntimeError):resolve_release(self.i.base,self.source.stat().st_uid)

if __name__=='__main__':unittest.main()
