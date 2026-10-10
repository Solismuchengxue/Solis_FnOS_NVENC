# SPDX-License-Identifier: GPL-3.0-or-later
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from nvenc_cli import menu, parser, confirm_idle, action_argv, licensed, execute

class MenuTests(unittest.TestCase):
    def test_exit_never_invokes_privileged_action(self):
        calls=[];output=[]
        self.assertEqual(menu(lambda prompt:'0',output.append,calls.append),0)
        self.assertEqual(calls,[])
    def test_invalid_input_and_eof_do_not_deploy(self):
        replies=iter(['bad','999']);calls=[];output=[]
        def read(prompt):
            try:return next(replies)
            except StopIteration:raise EOFError
        self.assertEqual(menu(read,output.append,calls.append),0)
        self.assertEqual(calls,[])
    def test_install_choice_routes_to_full_install(self):
        replies=iter(['2','0']);calls=[]
        menu(lambda prompt:next(replies),lambda value:None,calls.append)
        self.assertEqual(calls,['install'])
    def test_legacy_commands_remain_available(self):
        for action in ('check','deploy','status','rollback'):
            self.assertEqual(parser().parse_args([action]).action,action)
    def test_closed_stdin_is_not_an_idle_confirmation(self):
        with self.assertRaises(RuntimeError):confirm_idle(False,io.StringIO(''))
    def test_unaffirmed_answer_cancels_service_change(self):
        with self.assertRaises(RuntimeError):confirm_idle(False,io.StringIO('no\n'))
    def test_menu_sudo_preserves_selected_action(self):
        args=parser().parse_args(['install','--bundle','/safe/bundle','--idle-confirmed'])
        self.assertEqual(action_argv(args),['install','--bundle','/safe/bundle','--idle-confirmed'])
    def test_unknown_or_unlicensed_status_is_not_accepted(self):
        self.assertTrue(licensed('    License Status : Licensed (Expiry: omitted)'))
        self.assertFalse(licensed('    License Status : Unlicensed'))
        self.assertFalse(licensed('N/A'))

    def test_owned_hook_can_be_revoked_before_damaged_bundle_selection(self):
        with patch('nvenc_autostart.AutoController') as auto, patch('nvenc_cli.choose_bundle',side_effect=RuntimeError('damaged bundle')), patch('nvenc_cli.os.geteuid',return_value=0):
            auto.return_value.owned_hook.return_value=True
            auto.return_value.disable.return_value={'operation':'CONFIG_DISABLED_NOT_RESTORED'}
            self.assertEqual(execute(parser().parse_args(['disable','--idle-confirmed']))['operation'],'CONFIG_DISABLED_NOT_RESTORED')

if __name__=='__main__':unittest.main()
