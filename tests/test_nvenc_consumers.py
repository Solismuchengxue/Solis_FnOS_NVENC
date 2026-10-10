"""Reject real consumers without confusing them with frozen FIFO transport."""
import hashlib,json,os,pathlib,subprocess,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from consumer_fixture import HELPER

@unittest.skipUnless(sys.platform=='linux','real Linux procfs/FIFO tests')
class ConsumerTests(unittest.TestCase):
    def run_guard(self,external=None,resource=False,bad_binding=False):
        with tempfile.TemporaryDirectory(prefix='nvenc-consumers-') as folder:
            base=pathlib.Path(folder);p=base/'P';s=base/'S';p.mkdir();s.mkdir()
            opened=p/'input';opened.write_bytes(b'local fixture')
            context=base/'context.json'
            target=[sys.executable,'-B',str(pathlib.Path(__file__).parent/'consumer_fixture.py'),str(context),str(p),str(s)]
            args=['/bin/sh','-c',HELPER,'sh',str(opened) if resource else '-',*target]
            digest=hashlib.sha256(pathlib.Path('/bin/sh').resolve().read_bytes()).hexdigest()
            context.write_text(json.dumps({'marker':folder,'helper_argv':args if not bad_binding else args+['drift'],'helper_exe_sha256':digest}))
            child=None
            try:
                if external:
                    argument=str(p)+'_other' if external=='prefix' else str(p)
                    child=subprocess.Popen(['/bin/sh','-c','read unused','external-fixture',argument],stdin=subprocess.PIPE,cwd=p if external=='cwd' else base)
                run=subprocess.run(args,capture_output=True,text=True,timeout=15)
                self.assertEqual(run.returncode,0,run.stderr)
                for line in run.stdout.splitlines():
                    if line.startswith('TARGET_OUT '):
                        import base64
                        return json.loads(base64.b64decode(line.split(' ',1)[1]))
                self.fail('fixture did not return a bounded result')
            finally:
                if child:
                    child.terminate();child.wait(timeout=5);child.stdin.close()

    def test_own_fifo_transport_is_not_an_external_consumer(self):
        self.assertEqual(self.run_guard()['result'],'PASS')

    def test_same_user_shell_outside_control_family_blocks_cleanup(self):
        self.assertEqual(self.run_guard(external='argv')['result'],'REFUSED')

    def test_real_file_open_in_capture_family_still_blocks_cleanup(self):
        self.assertEqual(self.run_guard(resource=True)['result'],'REFUSED')

    def test_external_current_directory_blocks_cleanup(self):
        self.assertEqual(self.run_guard(external='cwd')['result'],'REFUSED')

    def test_unknown_transport_binding_is_not_whitelisted(self):
        self.assertEqual(self.run_guard(bad_binding=True)['result'],'REFUSED')

    def test_different_path_with_same_prefix_is_not_this_scope(self):
        self.assertEqual(self.run_guard(external='prefix')['result'],'PASS')

if __name__=='__main__':unittest.main()
