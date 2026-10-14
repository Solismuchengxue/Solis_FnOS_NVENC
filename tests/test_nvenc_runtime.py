"""Real filesystem controller tests, with service/GPU boundaries supplied by a fake host."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
try:
    from nvenc_runtime import Controller, Refused, DROPIN, STATE, PREFIX
except ImportError:
    Controller = None
    Refused = RuntimeError
    DROPIN = "/run/systemd/system/mediasrv.service.d/95-solis-nvenc-managed.conf"
    STATE = "/var/lib/solis-fnos-nvenc/state.json"
    PREFIX = "/opt/solis-fnos-nvenc/managed"

def digest(data): return hashlib.sha256(data).hexdigest()

class Host:
    def __init__(self, root):
        self.root=root; self.restarts=0; self.fail_next=False; self.busy=False
        self.api=0xC1; self.driver="535.309.01"; self.gpu="GRID P4-4Q"; self.loaded="/official/libavcodec.so.62"
        self.env="LD_LIBRARY_PATH=/official"; self.boot="boot-current"
    def info(self):
        return {"arch":"x86_64","os":"12","glibc":"2.36","driver":self.driver,"gpu":self.gpu,"api":self.api,"boot":self.boot}
    def service(self):
        directory=self.root/'run/systemd/system/mediasrv.service.d'
        dropins=['/'+str(p.relative_to(self.root)) for p in sorted(directory.glob('*.conf'))] if directory.exists() else []
        return {"active":True,"pid":731,"environment":self.env,"loaded":self.loaded,"dropins":dropins}
    def idle(self):
        if self.busy: raise Refused("正在播放或转码")
    def load_check(self, lib, profile): return {"abi":62,"deps":"PASS"}
    def restart(self):
        self.restarts+=1
        if self.fail_next:
            self.fail_next=False
            raise RuntimeError("injected service restart failure")
        p=self.root/DROPIN.lstrip('/')
        if p.exists():
            text=p.read_text(); location=text.split('LD_LIBRARY_PATH=',1)[1].split(':',1)[0]
            self.loaded=location+"/libavcodec.so.62"
            self.env="LD_LIBRARY_PATH="+location+":/official"
        else:
            self.loaded="/official/libavcodec.so.62";self.env="LD_LIBRARY_PATH=/official"

@unittest.skipUnless(sys.platform=='linux','需要 Linux 权限和符号链接合同；Windows 只做 parser 检查')
class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.bundle=self.root/"bundle";self.bundle.mkdir()
        (self.bundle/"libavcodec.so.62").write_bytes(b"private candidate")
        for name,data in (("/official/libavcodec.so.62",b"official"),("/official/mediasrv",b"service"),("/etc/systemd/system/mediasrv.service",b"unit")):
            p=self.root/name.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.profile={"schema":1,"id":"known-test","nas_tool_verified":True,"arch":"x86_64","os":"12","glibc":"2.36","driver":"535.309.01","candidate_api":0xC1,"official_api":0xD0,"candidate_sha256":digest(b"private candidate"),"files":{p:digest((self.root/p.lstrip('/')).read_bytes()) for p in ("/official/libavcodec.so.62","/official/mediasrv","/etc/systemd/system/mediasrv.service")},"official_dir":"/official","allowed_baseline":{"/official/libavcodec.so.62":digest(b"official")},"allowed_dropins":{}}
        self.host=Host(self.root)
        self.profile["gpu"]="GRID P4-4Q"
        self.profile["dependencies"]={}
        self.assertIsNotNone(Controller,"缺少部署入口，期望可检查并部署已知兼容组合")
        self.c=Controller(self.root,self.bundle,self.profile,self.host)
    def tearDown(self): self.temp.cleanup()
    def state(self): return json.loads((self.root/STATE.lstrip('/')).read_text())
    def test_deploy_idempotent_and_rollback(self):
        self.assertEqual(self.c.check()["compatibility"],"PASS")
        self.assertEqual(self.c.deploy()["operation"],"DEPLOYED")
        self.assertEqual(self.host.restarts,1)
        self.assertEqual(self.c.status()["loaded"],True)
        self.assertEqual(self.c.status()["transcode"],"NOT_VERIFIED")
        self.assertEqual(self.c.deploy()["operation"],"ALREADY_LOADED")
        self.assertEqual(self.host.restarts,1)
        self.assertEqual(self.c.rollback()["operation"],"RESTORED")
        self.assertEqual(self.host.restarts,2)
        self.assertEqual(self.host.loaded,"/official/libavcodec.so.62")
        self.assertFalse((self.root/DROPIN.lstrip('/')).exists())
        self.assertEqual((self.root/"official/libavcodec.so.62").read_bytes(),b"official")
        self.assertEqual(self.c.rollback()["operation"],"ALREADY_INACTIVE")
    def test_failure_restores_actual_baseline(self):
        self.host.fail_next=True
        with self.assertRaises(RuntimeError): self.c.deploy()
        self.assertEqual(self.host.loaded,"/official/libavcodec.so.62")
        self.assertFalse((self.root/DROPIN.lstrip('/')).exists())
        self.assertEqual(self.state()["phase"],"restored_after_failure")
    def test_legacy_deploy_and_rollback_leave_no_owned_residue_after_uninstall(self):
        from nvenc_install import Installer
        self.c.deploy();self.c.rollback()
        Installer(self.root,required_uid=self.root.stat().st_uid).uninstall(lambda roots:None)
        self.assertFalse((self.root/'opt/solis-fnos-nvenc').exists())
        self.assertFalse((self.root/'var/lib/solis-fnos-nvenc').exists())
        self.assertFalse((self.root/'run/systemd/system/mediasrv.service.d').exists())
        self.assertEqual((self.root/'official/libavcodec.so.62').read_bytes(),b'official')
    def test_cli_recovery_gate_checks_legacy_actual_service_and_current_boot(self):
        from nvenc_cli import verify_tool_recovery
        from nvenc_autostart import AutoController
        self.c.deploy();self.c.rollback()
        boot=self.root/'proc/sys/kernel/random/boot_id';boot.parent.mkdir(parents=True);boot.write_text(self.host.boot)
        auto=AutoController(self.root,self.bundle,self.profile,self.host)
        self.host.loaded='/different/libavcodec.so.62'
        with self.assertRaises(Refused):verify_tool_recovery(auto)
        self.host.loaded='/official/libavcodec.so.62';boot.write_text('another-boot')
        with self.assertRaises(Refused):verify_tool_recovery(auto)
        boot.write_text(self.host.boot);verify_tool_recovery(auto)
    def test_unknown_version_refused_without_mutation(self):
        self.host.driver="999.1"
        with self.assertRaises(Refused):self.c.deploy()
        self.assertFalse((self.root/STATE.lstrip('/')).exists())
        self.assertEqual(self.host.restarts,0)
    def test_upgraded_components_refused(self):
        (self.root/"official/mediasrv").write_bytes(b"new app")
        with self.assertRaises(Refused):self.c.deploy()
        self.assertEqual(self.host.restarts,0)
    def test_artifact_corruption_refused(self):
        (self.bundle/"libavcodec.so.62").write_bytes(b"bad")
        with self.assertRaises(Refused):self.c.deploy()
    def test_busy_refused(self):
        self.host.busy=True
        with self.assertRaises(Refused):self.c.deploy()
        self.assertEqual(self.host.restarts,0)
    def test_foreign_dropin_preserved(self):
        p=self.root/DROPIN.lstrip('/');p.parent.mkdir(parents=True);p.write_bytes(b"foreign")
        with self.assertRaises(Refused):self.c.deploy()
        self.assertEqual(p.read_bytes(),b"foreign")
    def test_symlink_parent_refused(self):
        outside=self.root/"outside";outside.mkdir()
        p=self.root/"opt";p.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(Refused):self.c.deploy()
        self.assertEqual(list(outside.iterdir()),[])
    def test_unknown_baseline_refused(self):
        self.host.loaded="/other/libavcodec.so.62"
        with self.assertRaises(Refused):self.c.deploy()
    def test_drift_before_rollback_preserves_managed_dropin(self):
        self.c.deploy();(self.root/"official/mediasrv").write_bytes(b"upgrade")
        with self.assertRaises(Refused):self.c.rollback()
        self.assertTrue((self.root/DROPIN.lstrip('/')).exists())
        self.assertEqual(self.host.restarts,1)
    def test_failed_recovery_is_visible(self):
        def broken(): self.host.restarts+=1;raise RuntimeError("both restarts fail")
        self.host.restart=broken
        with self.assertRaisesRegex(RuntimeError,"恢复失败"):self.c.deploy()
        self.assertEqual(self.state()["phase"],"recovery_required")
    def test_profile_not_nas_verified_refuses_deploy(self):
        self.profile["nas_tool_verified"]=False
        with self.assertRaisesRegex(Refused,"NAS"):self.c.deploy()
        self.assertEqual(self.host.restarts,0)
    def test_official_api_sufficient_prompts_no_patch(self):
        self.host.api=0xD0
        self.assertEqual(self.c.check()["compatibility"],"OFFICIAL_API_SUFFICIENT")
        with self.assertRaisesRegex(Refused,"官方"):self.c.deploy()
    def test_restart_or_upgrade_needs_new_baseline(self):
        self.c.deploy();(self.root/DROPIN.lstrip('/')).unlink()
        self.host.boot="next-boot";self.host.loaded="/official/libavcodec.so.62";self.host.env="LD_LIBRARY_PATH=/official"
        self.assertEqual(self.c.status()["loaded"],False)
        self.c.deploy()
        self.assertEqual(self.state()["baseline"]["boot"],"next-boot")
    def test_restore_historical_current_not_official(self):
        old="/historical/libavcodec.so.62";p=self.root/old.lstrip('/');p.parent.mkdir();p.write_bytes(b"historical")
        self.profile["allowed_baseline"][old]=digest(b"historical")
        oldconf="/run/systemd/system/mediasrv.service.d/90-existing.conf";p=self.root/oldconf.lstrip('/');p.parent.mkdir(parents=True);p.write_bytes(b"old override")
        self.profile["allowed_dropins"][oldconf]=digest(b"old override")
        self.host.loaded=old;self.host.env="LD_LIBRARY_PATH=/historical:/official"
        original=self.host.restart
        def restart():
            original()
            if not (self.root/DROPIN.lstrip('/')).exists():self.host.loaded=old;self.host.env="LD_LIBRARY_PATH=/historical:/official"
        self.host.restart=restart
        self.c.deploy();self.c.rollback()
        self.assertEqual(self.host.loaded,old)
        self.assertEqual(p.read_bytes(),b"old override")

    def test_wrong_gpu_refused(self):
        self.host.gpu="Unknown GPU"
        with self.assertRaises(Refused):self.c.deploy()
        self.assertEqual(self.host.restarts,0)
    def test_rollback_failure_marks_recovery(self):
        self.c.deploy();self.host.fail_next=True
        with self.assertRaisesRegex(RuntimeError,"恢复失败"):self.c.rollback()
        self.assertEqual(self.state()["phase"],"recovery_required")
    def test_status_detects_component_upgrade(self):
        self.c.deploy();(self.root/"official/mediasrv").write_bytes(b"upgrade")
        with self.assertRaises(Refused):self.c.status()
    def test_official_api_sufficient_on_new_driver_without_bundle(self):
        self.host.api=0xD0;self.host.driver="future-driver"
        (self.bundle/"libavcodec.so.62").unlink()
        self.assertEqual(self.c.check()["compatibility"],"OFFICIAL_API_SUFFICIENT")
    def test_copy_race_cannot_load_changed_artifact(self):
        def idle(): (self.bundle/"libavcodec.so.62").write_bytes(b"changed after check")
        self.host.idle=idle
        with self.assertRaises(Refused):self.c.deploy()
        self.assertEqual(self.host.restarts,0)
    def test_redeploy_retains_previous_restore_record(self):
        self.c.deploy();self.c.rollback();old=(self.root/STATE.lstrip('/')).read_bytes()
        self.c.deploy()
        previous=list((self.root/STATE.lstrip('/')).parent.glob('previous-*.json'))
        self.assertTrue(any(p.read_bytes()==old for p in previous))
    def test_unknown_dropin_appearing_before_rollback_stops(self):
        self.c.deploy();original=self.host.service
        def service():
            s=original();s['dropins'].append('/run/systemd/system/mediasrv.service.d/99-other.conf');return s
        self.host.service=service
        with self.assertRaises(Refused):self.c.rollback()
        self.assertTrue((self.root/DROPIN.lstrip('/')).exists())
        self.assertEqual(self.host.restarts,1)
    def test_rollback_does_not_require_healthy_source_bundle(self):
        self.c.deploy();(self.bundle/"libavcodec.so.62").write_bytes(b"corrupt bundle")
        self.assertEqual(self.c.rollback()["operation"],"RESTORED")
        self.assertEqual(self.host.loaded,"/official/libavcodec.so.62")
    def test_unknown_dependency_identity_refused(self):
        self.profile['dependencies']=None
        with self.assertRaises(Refused):self.c.deploy()
        self.assertEqual(self.host.restarts,0)
    def test_changed_dependency_refused(self):
        self.profile['dependencies']={'/system/libdep.so':'known-sha'}
        self.host.load_check=lambda lib,p:{'abi':62,'deps':'PASS','identities':{'/system/libdep.so':'changed-sha'}}
        with self.assertRaises(Refused):self.c.deploy()
        self.assertEqual(self.host.restarts,0)
    def test_approved_upgrade_profile_uses_new_actual_baseline(self):
        self.c.deploy();self.c.rollback()
        old=(self.root/STATE.lstrip('/')).read_bytes()
        p=self.root/'official/libavcodec.so.62';p.write_bytes(b'approved new official')
        self.profile['files']['/official/libavcodec.so.62']=digest(p.read_bytes())
        self.profile['allowed_baseline']['/official/libavcodec.so.62']=digest(p.read_bytes())
        self.profile['id']='known-approved-v2'
        self.host.boot='new-approved-boot'
        self.assertEqual(self.c.deploy()['operation'],'DEPLOYED')
        self.assertEqual(self.state()['profile'],'known-approved-v2')
        self.assertEqual(self.state()['baseline']['loaded_identity']['sha256'],digest(b'approved new official'))
        self.assertEqual(self.c.rollback()['operation'],'RESTORED')
        self.assertTrue(any(f.read_bytes()==old for f in (self.root/STATE.lstrip('/')).parent.glob('previous-*.json')))

    def trial_contract(self):
        self.profile['nas_tool_verified']=False
        self.c.trial={'schema':1,'authorization_id':'fresh-human-approval','profile_sha256':digest(json.dumps(self.profile,sort_keys=True,separators=(',',':')).encode()),'boot':'boot-current','expires_at':time.time()+900,'baseline':self.c.snapshot()}

    def test_frozen_trial_allows_one_cycle_without_claiming_verified(self):
        self.trial_contract()
        self.assertEqual(self.c.deploy()['operation'],'DEPLOYED')
        self.assertFalse(self.profile['nas_tool_verified'])
        self.assertEqual(self.c.deploy()['operation'],'ALREADY_LOADED')
        self.assertEqual(self.host.restarts,1)
        self.c.trial['expires_at']=0
        self.assertEqual(self.c.rollback()['operation'],'RESTORED')
        self.assertFalse(self.profile['nas_tool_verified'])

    def test_trial_cannot_be_replayed_after_restoration(self):
        self.trial_contract();self.c.deploy();self.c.rollback()
        with self.assertRaisesRegex(Refused,'试用'):self.c.deploy()
        self.assertEqual(self.host.restarts,2)

    def test_trial_expiration_refuses_before_switch(self):
        self.trial_contract();self.c.trial['expires_at']=0
        with self.assertRaisesRegex(Refused,'试用'):self.c.deploy()
        self.assertEqual(self.host.restarts,0)

    def test_trial_different_boot_refuses_before_switch(self):
        self.trial_contract();self.host.boot='another-boot'
        with self.assertRaisesRegex(Refused,'试用'):self.c.deploy()
        self.assertEqual(self.host.restarts,0)

    def test_trial_profile_drift_refuses_before_switch(self):
        self.trial_contract();self.profile['id']='different-profile'
        with self.assertRaisesRegex(Refused,'试用'):self.c.deploy()
        self.assertEqual(self.host.restarts,0)

    def test_trial_actual_baseline_drift_refuses_before_switch(self):
        self.trial_contract();self.host.env='LD_LIBRARY_PATH=/changed'
        with self.assertRaisesRegex(Refused,'试用'):self.c.deploy()
        self.assertEqual(self.host.restarts,0)

    def test_loader_dependency_is_part_of_frozen_identity(self):
        from nvenc_runtime import LinuxHost
        loader=self.root/'loader.so';loader.write_bytes(b'loader fixture')
        self.profile['dependencies']={str(loader):digest(b'loader fixture')}
        def command(argv,env=None):
            if argv[:2]==['readelf','-d']:return 'Library soname: [libavcodec.so.62]'
            if argv[0]=='readelf':return 'GLIBC_2.35'
            if argv[0]=='ldd':return str(loader)+' (0x1234)'
            return '62'
        with patch('nvenc_runtime.run',side_effect=command):
            self.assertEqual(LinuxHost().load_check(self.bundle/'libavcodec.so.62',self.profile)['identities'],self.profile['dependencies'])

    def test_restart_waits_for_actual_codec_mapping(self):
        from nvenc_runtime import LinuxHost
        host=LinuxHost()
        with patch('nvenc_runtime.run',return_value=''),patch.object(host,'service',side_effect=[Refused('服务 codec 映射不唯一'),{'active':True,'pid':44,'loaded':'/ready/libavcodec.so.62'}]),patch('nvenc_runtime.time.sleep'):
            self.assertEqual(host.restart()['loaded'],'/ready/libavcodec.so.62')

if __name__=="__main__":unittest.main()
