# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from nvenc_build import fetch_sources, check_build_pair, BuildRefused

class BuildTests(unittest.TestCase):
    def test_verified_sources_downloaded_without_private_material(self):
        with tempfile.TemporaryDirectory() as folder:
            data=b'source'; entry={'name':'source.tar.xz','url':'https://ffmpeg.org/source.tar.xz','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            with patch('nvenc_build.urlopen',return_value=io.BytesIO(data)):
                fetch_sources({'files':[entry]},Path(folder))
            self.assertEqual((Path(folder)/entry['name']).read_bytes(),data)
    def test_hash_mismatch_never_becomes_source(self):
        with tempfile.TemporaryDirectory() as folder:
            entry={'name':'source','url':'https://ffmpeg.org/source','bytes':4,'sha256':'0'*64}
            with patch('nvenc_build.urlopen',return_value=io.BytesIO(b'evil')):
                with self.assertRaises(BuildRefused):fetch_sources({'files':[entry]},Path(folder))
            self.assertFalse((Path(folder)/'source').exists())
    def test_existing_corrupted_cache_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source';path.write_bytes(b'old')
            entry={'name':'source','url':'https://ffmpeg.org/source','bytes':3,'sha256':'0'*64}
            with self.assertRaises(BuildRefused):fetch_sources({'files':[entry]},Path(folder))
            self.assertEqual(path.read_bytes(),b'old')
    def test_download_path_escape_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(BuildRefused):fetch_sources({'files':[{'name':'../evil'}]},Path(folder))
    def test_matching_rebuild_does_not_waive_approved_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a';b=Path(folder)/'b';a.write_bytes(b'new');b.write_bytes(b'new')
            with self.assertRaises(BuildRefused):check_build_pair(a,b,'0'*64,3)
            b.write_bytes(b'other')
            with self.assertRaises(BuildRefused):check_build_pair(a,b,hashlib.sha256(b'new').hexdigest(),3)
    def test_source_manifest_bound_to_existing_profile(self):
        root=Path(__file__).resolve().parents[1]
        m=json.loads((root/'build/build_sources.json').read_text())
        p=json.loads((root/'metadata/runtime_profile.json').read_text())
        self.assertEqual(m['candidate_sha256'],p['candidate_sha256'])
        self.assertEqual(hashlib.sha256((root/'build/build_packages.txt').read_bytes()).hexdigest(),m['package_list_sha256'])
        self.assertEqual(len(m['base_image'].split('sha256:')[1]),64)

if __name__=='__main__':unittest.main()
