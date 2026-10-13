# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_nvenc_runtime as legacy
from nvenc_autostart import AutoController, AUTO_DROPIN, ENV_FILE, AUTO_STATE, TRIAL
from nvenc_install import atomic_json
from nvenc_runtime import Refused, sha

class AutoTests(legacy.RuntimeTests):
    def setUp(self):
        super().setUp();self.profile['nas_tool_verified']=True
        self.c=AutoController(self.root,self.bundle,self.profile,self.host,verified=True)
        self.host.reloads=0
        def reload():self.host.reloads+=1
        self.host.reload=reload
        def restart():
            self.host.restarts+=1
            if self.host.fail_next:self.host.fail_next=False;raise RuntimeError('restart failure')
            self.c.boot_prepare()
            env=self.root/ENV_FILE.lstrip('/')
            if env.exists() and env.read_text():
                value=env.read_text().strip().split('=',1)[1];self.host.env='LD_LIBRARY_PATH='+value
                self.host.loaded=value.split(':')[0]+'/libavcodec.so.62'
            else:self.host.loaded='/official/libavcodec.so.62';self.host.env='LD_LIBRARY_PATH=/official'
        self.host.restart=restart
        original=self.host.service
        def service():
            result=original();path=self.root/AUTO_DROPIN.lstrip('/')
            if path.exists():result['dropins'].append(AUTO_DROPIN)
            return result
        self.host.service=service
    def test_enable_repeated_and_disable_restore(self):
        self.assertEqual(self.c.enable()['operation'],'AUTO_ENABLED')
        self.assertEqual(self.c.enable()['operation'],'ALREADY_LOADED')
        self.assertEqual(self.host.restarts,1)
        self.assertEqual(self.c.disable()['operation'],'RESTORED')
        self.assertEqual(self.host.loaded,'/official/libavcodec.so.62')
        self.assertFalse((self.root/AUTO_DROPIN.lstrip('/')).exists())
    def test_boot_drift_empties_injection_and_keeps_config(self):
        self.c.enable();self.host.driver='changed';self.host.boot='new-boot'
        result=self.c.boot_prepare()
        self.assertEqual(result['startup'],'SKIPPED')
        self.assertEqual((self.root/ENV_FILE.lstrip('/')).read_bytes(),b'')
        self.assertTrue((self.root/AUTO_DROPIN.lstrip('/')).exists())
    def test_new_boot_does_not_replay_original_baseline(self):
        self.c.enable();self.host.boot='new-boot';self.host.loaded=None;self.host.env='LD_LIBRARY_PATH=/official'
        result=self.c.boot_prepare()
        self.assertEqual(result['startup'],'PREPARED')
        state=json.loads((self.root/AUTO_STATE.lstrip('/')).read_text())
        self.assertEqual(state['baseline']['boot'],'new-boot')
        self.assertEqual(state['baseline']['loaded'],'/official/libavcodec.so.62')
        self.assertEqual(state['baseline']['proof'],'CONFIG_BEFORE_START')
    def test_boot_baseline_includes_fixed_official_search_directory(self):
        self.host.env='LD_LIBRARY_PATH=/usr/trim/lib';self.host.loaded=None
        self.assertEqual(self.c.boot_baseline()['loaded'],'/official/libavcodec.so.62')
    def test_failed_enable_restores_original(self):
        self.host.fail_next=True
        with self.assertRaises(RuntimeError):self.c.enable()
        self.assertEqual(self.host.loaded,'/official/libavcodec.so.62')
        self.assertFalse((self.root/AUTO_DROPIN.lstrip('/')).exists())
    def test_busy_does_not_create_persistent_config(self):
        self.host.busy=True
        with self.assertRaises(RuntimeError):self.c.enable()
        self.assertFalse((self.root/AUTO_DROPIN.lstrip('/')).exists())
    def test_unknown_persistent_config_preserved(self):
        path=self.root/AUTO_DROPIN.lstrip('/');path.parent.mkdir(parents=True);path.write_bytes(b'foreign')
        with self.assertRaises(RuntimeError):self.c.enable()
        self.assertEqual(path.read_bytes(),b'foreign')
    def test_autostart_unverified_gate_closed(self):
        self.c.verified=False
        with self.assertRaises(RuntimeError):self.c.enable()
        self.assertFalse((self.root/AUTO_DROPIN.lstrip('/')).exists())
    def test_old_installer_acceptance_cannot_enable_unverified_profile(self):
        self.profile['nas_tool_verified']=False
        with self.assertRaises(Refused):self.c.enable()
        self.assertFalse((self.root/AUTO_DROPIN.lstrip('/')).exists())
        self.assertFalse((self.root/AUTO_STATE.lstrip('/')).exists())
        self.assertEqual(self.host.restarts,0)
    def test_unverified_profile_clears_startup_injection_and_can_restore(self):
        self.c.enable();restarts=self.host.restarts
        self.profile['nas_tool_verified']=False
        self.assertEqual(self.c.boot_prepare()['startup'],'SKIPPED')
        self.assertEqual((self.root/ENV_FILE.lstrip('/')).read_bytes(),b'')
        self.assertTrue((self.root/AUTO_DROPIN.lstrip('/')).is_file())
        self.assertEqual(self.host.restarts,restarts)
        self.assertEqual(self.c.disable()['operation'],'RESTORED')
        self.assertEqual(self.host.loaded,'/official/libavcodec.so.62')
    def test_unverified_profile_status_does_not_reuse_installer_acceptance(self):
        self.profile['nas_tool_verified']=False
        self.assertFalse(self.c.status()['autostart_verified'])
    def test_unverified_combination_requires_bound_unexpired_trial(self):
        self.profile['nas_tool_verified']=False;self.c.verified=False
        machine=self.root/'etc/machine-id';machine.parent.mkdir(parents=True,exist_ok=True)
        machine.write_bytes(b'local-test-machine')
        trial={'schema':1,'authorization':'user-approved-ssh-installer-v0.1.0',
               'profile_sha256':sha(json.dumps(self.profile,sort_keys=True).encode()),
               'machine_sha256':sha(b'local-test-machine'),'expires_at':time.time()+300,
               'initial_boot':'boot-current','allow_one_reboot':False}
        path=self.root/TRIAL.lstrip('/')
        for field,value in (('profile_sha256','0'*64),('machine_sha256','0'*64),
                            ('initial_boot','another-boot'),('expires_at',time.time()-1)):
            with self.subTest(field=field):
                invalid={**trial,field:value};atomic_json(path,invalid)
                with self.assertRaises(Refused):self.c.enable()
                self.assertFalse((self.root/AUTO_DROPIN.lstrip('/')).exists())
                self.assertEqual(self.host.restarts,0)
        atomic_json(path,trial)
        self.assertEqual(self.c.enable()['operation'],'AUTO_ENABLED')
        self.assertEqual(self.c.disable()['operation'],'RESTORED')
        self.assertEqual(self.host.loaded,'/official/libavcodec.so.62')
    def test_startup_hook_keeps_outer_transaction_reserved(self):
        observed=[]
        original=self.host.restart
        def restart():
            original()
            observed.append(self.c.state()['phase'])
            with self.assertRaises(RuntimeError):self.c.disable()
        self.host.restart=restart
        self.c.enable()
        self.assertEqual(observed,['switching'])
        self.assertEqual(self.c.state()['phase'],'loaded')
    def test_state_write_failure_never_leaves_injection(self):
        self.c.enable()
        with patch.object(self.c,'save_auto',side_effect=OSError('disk full')):
            self.assertEqual(self.c.boot_prepare()['startup'],'SKIPPED')
        self.assertEqual((self.root/ENV_FILE.lstrip('/')).read_bytes(),b'')
    def test_restore_retry_after_hook_removed_and_restart_failed(self):
        self.c.enable();self.host.fail_next=True
        with self.assertRaises(RuntimeError):self.c.disable()
        self.assertEqual(self.c.state()['phase'],'recovery_required')
        self.assertEqual(self.c.disable()['operation'],'RESTORED')
        self.assertEqual(self.host.loaded,'/official/libavcodec.so.62')
    def test_unknown_new_boot_can_revoke_own_config_without_old_state_replay(self):
        self.c.enable();self.host.boot='new-boot';self.host.driver='changed'
        self.c.boot_prepare();restarts=self.host.restarts
        result=self.c.disable()
        self.assertEqual(result['operation'],'CONFIG_DISABLED_NOT_RESTORED')
        self.assertEqual(self.host.restarts,restarts)
        self.assertFalse((self.root/AUTO_DROPIN.lstrip('/')).exists())
        self.assertEqual((self.root/ENV_FILE.lstrip('/')).read_bytes(),b'')
        self.assertGreater(self.host.reloads,0)
    def test_failed_transaction_cannot_revive_on_new_boot(self):
        self.c.enable();state=self.c.state();state['phase']='recovery_required';self.c.save_auto(state)
        self.host.boot='new-boot';self.host.loaded=None;self.host.env='LD_LIBRARY_PATH=/official'
        self.assertEqual(self.c.boot_prepare()['startup'],'SKIPPED')
        self.assertEqual((self.root/ENV_FILE.lstrip('/')).read_bytes(),b'')
    def test_hook_written_then_state_failure_is_revoked_without_restart(self):
        original=self.c.save_auto
        def save(state):
            if state['phase']=='switching':raise OSError('disk full')
            original(state)
        with patch.object(self.c,'save_auto',side_effect=save):
            with self.assertRaises(OSError):self.c.enable()
        self.assertFalse((self.root/AUTO_DROPIN.lstrip('/')).exists())
        self.assertEqual(self.host.restarts,0)
        self.assertNotEqual(self.c.boot_prepare()['startup'],'PREPARED')
    def test_abandoned_restoring_transaction_can_resume(self):
        self.c.enable();state=self.c.state();state.update(phase='restoring',enabled=False,owner={'pid':99999999,'ticks':'0','boot':self.host.boot})
        self.c.save_auto(state);(self.root/AUTO_DROPIN.lstrip('/')).unlink()
        self.assertEqual(self.c.disable()['operation'],'RESTORED')

    def test_install_cannot_replace_restoring_transaction_after_hook_removed(self):
        self.c.enable();original=self.host.restart
        def restart():
            state=self.c.state()
            self.assertEqual(state['phase'],'restoring')
            with self.assertRaises(RuntimeError):self.c.enable()
            self.assertEqual(self.c.state(),state)
            original()
        self.host.restart=restart
        self.assertEqual(self.c.disable()['operation'],'RESTORED')

    def test_missing_candidate_still_revokes_owned_config_without_restart(self):
        self.c.enable();restarts=self.host.restarts
        (self.bundle/'libavcodec.so.62').unlink()
        result=self.c.disable()
        self.assertEqual(result['operation'],'CONFIG_DISABLED_NOT_RESTORED')
        self.assertEqual(self.host.restarts,restarts)
        self.assertFalse((self.root/AUTO_DROPIN.lstrip('/')).exists())
        self.assertEqual((self.root/ENV_FILE.lstrip('/')).read_bytes(),b'')

# The inherited temporary-controller tests exercise another interface, already covered separately.
for name in list(vars(legacy.RuntimeTests)):
    if name.startswith('test_'):setattr(AutoTests,name,None)

if __name__=='__main__':unittest.main()
