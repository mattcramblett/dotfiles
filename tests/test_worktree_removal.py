import errno
import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from test_wta import BIN, ROOT, RepositoryFixture, worktrees


def session(number, path, *, tagged=True, name=None):
    return {"id": f"${number}", "name": name or f"task-{number}", "path": str(path),
            "tagged": tagged, "activity": number}


class RemovalTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.tmux.clients.return_value = []
        self.tmux.call.return_value = ""
        confirmation = patch.object(worktrees, "confirm_removal", return_value=True)
        self.confirm = confirmation.start()
        self.addCleanup(confirmation.stop)
        self.common = worktrees.repository(self.repo)
        self.branch = self.git(self.tree, "branch", "--show-current")
        self.registry.remember(self.common, str(self.tree), agent="pi", session_name="task")

    def remove(self, path=None):
        return worktrees.remove_worktree(str(path or self.tree), self.registry, self.tmux)

    def assert_preserved(self):
        self.assertTrue(self.tree.is_dir())
        self.tmux.call.assert_not_called()
        self.assertIn(str(self.tree), self.registry.read()["worktrees"])

    def test_removes_only_confirmed_exactly_tagged_sessions_after_git_success(self):
        affected = [session(1, self.tree, name="renamed-task"), session(2, self.tree)]
        self.tmux.sessions.return_value = [*affected, session(3, self.tree, tagged=False),
                                           session(4, self.tree / "nested"), session(5, self.repo)]
        transcript = self.root / "conversation.jsonl"
        transcript.write_text("synthetic conversation\n")
        self.registry.remember(self.common, str(self.repo), agent="pi")

        def kill(*args):
            self.assertFalse(self.tree.exists())
            self.assertNotIn(str(self.tree), self.registry.read()["worktrees"])
            return ""

        self.tmux.call.side_effect = kill
        with patch.object(worktrees, "run", wraps=worktrees.run) as execute:
            message = self.remove()
        self.assertIn("Branch preserved", message)
        self.assertFalse(self.tree.exists())
        self.git(self.repo, "show-ref", "--verify", "refs/heads/" + self.branch)
        self.assertEqual(transcript.read_text(), "synthetic conversation\n")
        self.assertIn(str(self.repo), self.registry.read()["worktrees"])
        self.assertIn(self.common, self.registry.read()["repositories"])
        self.confirm.assert_called_once_with(str(self.tree), self.branch, affected)
        self.tmux.call.assert_called_once_with("kill-session", "-t", "$1", ";", "kill-session", "-t", "$2")
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertIn(["git", "-C", self.common, "worktree", "remove", "--", str(self.tree)], commands)
        self.assertFalse(any("--force" in args for args in commands))

    def test_cancellation_does_not_remove_files_sessions_or_metadata(self):
        self.tmux.sessions.return_value = [session(1, self.tree)]
        self.confirm.return_value = False
        self.assertEqual(self.remove(), "Removal cancelled.")
        self.assert_preserved()

    def test_primary_worktree_is_rejected_before_confirmation(self):
        with self.assertRaisesRegex(worktrees.WorkspaceError, "primary"):
            self.remove(self.repo)
        self.confirm.assert_not_called()
        self.assert_preserved()

    def test_untracked_files_are_rejected_before_confirmation(self):
        (self.tree / "untracked.txt").write_text("preserve")
        with self.assertRaisesRegex(worktrees.WorkspaceError, "untracked"):
            self.remove()
        self.confirm.assert_not_called()
        self.assert_preserved()

    def test_modified_tracked_files_are_rejected(self):
        tracked = self.tree / "tracked.txt"
        tracked.write_text("initial")
        self.git(self.tree, "add", "tracked.txt")
        self.git(self.tree, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        tracked.write_text("modified")
        with self.assertRaisesRegex(worktrees.WorkspaceError, "uncommitted"):
            self.remove()
        self.assert_preserved()

    def test_locked_worktree_is_rejected_before_confirmation(self):
        self.git(self.repo, "worktree", "lock", str(self.tree))
        with self.assertRaisesRegex(worktrees.WorkspaceError, "locked"):
            self.remove()
        self.confirm.assert_not_called()
        self.assert_preserved()

    def test_subdirectory_is_not_treated_as_a_request_to_delete_its_worktree(self):
        directory = self.tree / "nested"
        directory.mkdir()
        with self.assertRaisesRegex(worktrees.WorkspaceError, "root"):
            self.remove(directory)
        self.confirm.assert_not_called()
        self.assert_preserved()

    def test_git_removal_failure_never_kills_sessions_or_discards_metadata(self):
        self.tmux.sessions.return_value = [session(1, self.tree)]
        original = worktrees.run

        def fail_remove(args, **kwargs):
            if "remove" in args:
                raise worktrees.WorkspaceError("synthetic Git removal failure")
            return original(args, **kwargs)

        with patch.object(worktrees, "run", side_effect=fail_remove), \
                self.assertRaisesRegex(worktrees.WorkspaceError, "Git removal failure"):
            self.remove()
        self.assert_preserved()

    def test_branch_changed_during_confirmation_is_rejected(self):
        def change_branch(*args):
            self.git(self.tree, "checkout", "-qb", "changed-task")
            return True

        self.confirm.side_effect = change_branch
        with self.assertRaisesRegex(worktrees.WorkspaceError, "identity changed"):
            self.remove()
        self.assert_preserved()

    def test_session_changes_during_confirmation_are_rejected(self):
        affected = session(1, self.tree)
        self.tmux.sessions.side_effect = [[affected], [affected, session(2, self.tree)]]
        with self.assertRaisesRegex(worktrees.WorkspaceError, "sessions changed"):
            self.remove()
        self.assert_preserved()

    def test_failed_session_inventory_is_not_treated_as_no_sessions(self):
        self.tmux.sessions.side_effect = worktrees.WorkspaceError("Cannot inspect sessions")
        with self.assertRaisesRegex(worktrees.WorkspaceError, "Cannot inspect"):
            self.remove()
        self.confirm.assert_not_called()
        self.assert_preserved()

    def test_new_unconfirmed_session_after_removal_is_not_killed(self):
        affected = session(1, self.tree)
        self.tmux.sessions.side_effect = [[affected], [affected], [affected, session(2, self.tree)]]
        with self.assertRaisesRegex(worktrees.WorkspaceError, "Removed worktree.*Unconfirmed"):
            self.remove()
        self.assertFalse(self.tree.exists())
        self.tmux.call.assert_not_called()
        self.assertNotIn(str(self.tree), self.registry.read()["worktrees"])

    def test_retagged_session_after_removal_is_not_killed(self):
        affected = session(1, self.tree)
        self.tmux.sessions.side_effect = [[affected], [affected], [session(1, self.repo)]]
        with self.assertRaisesRegex(worktrees.WorkspaceError, "changed identity"):
            self.remove()
        self.assertFalse(self.tree.exists())
        self.tmux.call.assert_not_called()

    def test_session_cleanup_failure_reports_that_git_removal_already_succeeded(self):
        self.tmux.sessions.return_value = [session(1, self.tree)]
        self.tmux.call.side_effect = worktrees.WorkspaceError("synthetic tmux failure")
        with self.assertRaisesRegex(worktrees.WorkspaceError, "Removed worktree.*cleanup failed"):
            self.remove()
        self.assertFalse(self.tree.exists())
        self.assertNotIn(str(self.tree), self.registry.read()["worktrees"])
        self.git(self.repo, "show-ref", "--verify", "refs/heads/" + self.branch)

    def test_clients_switch_to_an_unrelated_session_before_the_confirmed_session_is_killed(self):
        self.tmux.sessions.return_value = [session(1, self.tree), session(2, self.repo)]
        self.tmux.clients.return_value = [{"name": "/dev/tty-fixture", "session": "$1"}]
        self.remove()
        self.tmux.call.assert_called_once_with("switch-client", "-c", "/dev/tty-fixture", "-t", "$2", ";",
                                                "kill-session", "-t", "$1")

    def test_invoking_panes_session_is_closed_last(self):
        self.tmux.sessions.return_value = [session(1, self.tree), session(2, self.tree)]
        self.tmux.value.return_value = "$1"
        with patch.dict(os.environ, {"TMUX_PANE": "%3"}):
            self.remove()
        self.tmux.value.assert_called_once_with("%3", "#{session_id}")
        self.tmux.call.assert_called_once_with("kill-session", "-t", "$2", ";", "kill-session", "-t", "$1")

    def test_last_attached_session_gets_a_home_shell_fallback(self):
        self.tmux.sessions.return_value = [session(1, self.tree), session(2, self.tree, tagged=False)]
        self.tmux.clients.return_value = [{"name": "/dev/tty-fixture", "session": "$1"}]
        self.tmux.call.side_effect = ["$9", ""]
        self.remove()
        self.assertEqual(self.tmux.call.call_args_list[0].args,
                         ("new-session", "-d", "-P", "-F", "#{session_id}", "-c", str(Path.home())))
        self.assertEqual(self.tmux.call.call_args_list[1].args,
                         ("switch-client", "-c", "/dev/tty-fixture", "-t", "$9", ";", "kill-session", "-t", "$1"))

    def test_no_tagged_sessions_does_not_touch_unrelated_sessions(self):
        self.tmux.sessions.return_value = [session(1, self.tree, tagged=False)]
        self.remove()
        self.tmux.call.assert_not_called()
        self.tmux.clients.assert_not_called()

    def test_unusual_path_is_passed_as_one_git_argument(self):
        unusual = self.add_tree(self.repo, self.root / "spaces 'quotes'; $(nope)\tnew\nline", "unusual")
        self.remove(unusual)
        self.assertFalse(unusual.exists())
        self.git(self.repo, "show-ref", "--verify", "refs/heads/unusual")

    def test_linked_worktree_of_a_bare_repository_can_be_removed(self):
        bare = self.root / "bare.git"
        self.git(self.repo, "clone", "--bare", str(self.repo), str(bare))
        tree = self.add_tree(bare, self.root / "bare-task", "bare-task")
        self.remove(tree)
        self.assertFalse(tree.exists())
        self.assertTrue(bare.exists())
        self.git(bare, "show-ref", "--verify", "refs/heads/bare-task")

    def test_removing_from_inside_the_worktree_keeps_the_picker_in_a_valid_directory(self):
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.tree)
        with patch.object(worktrees.Path, "home", return_value=self.root):
            self.remove()
        self.assertEqual(Path.cwd(), self.root)


class SessionInventoryTests(unittest.TestCase):
    def test_strict_inventory_rejects_unexpected_tmux_errors(self):
        failure = subprocess.CompletedProcess([], 1, "", "permission denied")
        with (patch.object(worktrees.shutil, "which", return_value="/tmux"),
              patch.object(worktrees, "run", return_value=failure),
              self.assertRaisesRegex(worktrees.WorkspaceError, "permission denied")):
            worktrees.Tmux().sessions(strict=True)

    def test_no_running_server_is_an_empty_inventory(self):
        absent = subprocess.CompletedProcess([], 1, "", "no server running")
        with patch.object(worktrees.shutil, "which", return_value="/tmux"), patch.object(worktrees, "run", return_value=absent):
            self.assertEqual(worktrees.Tmux().sessions(strict=True), [])

    def test_strict_inventory_rejects_malformed_records_and_relative_tags(self):
        for record in ["unreadable", "$1\x1ftask\x1frelative/path\x1f/repo\x1f1",
                       "$1\x1ftask\x1f/repo\x1f/repo\x1fnot-a-number"]:
            with (self.subTest(record=record), patch.object(worktrees.shutil, "which", return_value="/tmux"),
                  patch.object(worktrees, "run", return_value=subprocess.CompletedProcess([], 0, record, "")),
                  self.assertRaises(worktrees.WorkspaceError)):
                worktrees.Tmux().sessions(strict=True)

    def test_confirmation_lists_sessions_and_warns_about_running_commands(self):
        terminal = mock_open(read_data="n\n")
        with patch("builtins.open", terminal):
            self.assertFalse(worktrees.confirm_removal("/repo/line\nbreak", "topic", [session(1, "/repo", name="renamed")]))
        prompt = "".join(call.args[0] for call in terminal().write.call_args_list)
        self.assertIn("$1  renamed", prompt)
        self.assertIn("running agents/commands", prompt)
        self.assertIn("/repo/line\\nbreak", prompt)
        self.assertNotIn("/repo/line\nbreak", prompt)
        self.assertIn("Git branch is preserved", prompt)
        self.assertIn("including ignored files", prompt)
        self.assertIn("conversation files outside the worktree are not deleted", prompt)

    def test_missing_controlling_terminal_never_silently_approves_removal(self):
        with patch("builtins.open", side_effect=OSError("no tty")), \
                self.assertRaisesRegex(worktrees.WorkspaceError, "nothing was removed"):
            worktrees.confirm_removal("/repo", "topic", [])


class PickerRemovalTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.tmux.matching.side_effect = worktrees.Tmux().matching

    def test_ctrl_x_refreshes_all_registered_repositories_and_preserves_the_query(self):
        second = self.make_repo(self.root / "another")
        self.register()
        self.register(second)
        snapshots = []

        def choose(rows, query, notice):
            snapshots.append((rows, query, notice))
            if len(snapshots) == 1:
                return str(self.tree), True, "kept filter"
            return None

        with patch.object(worktrees, "pick", side_effect=choose), \
                patch.object(worktrees, "confirm_removal", return_value=True), \
                patch.object(worktrees, "Tmux", return_value=self.tmux), \
                patch.object(worktrees, "attach_worktree") as attach:
            worktrees.wta_main([])
        self.assertEqual(len(snapshots), 2)
        self.assertEqual({row["path"] for row in snapshots[0][0]}, {str(self.repo), str(self.tree), str(second)})
        self.assertEqual({row["path"] for row in snapshots[1][0]}, {str(self.repo), str(second)})
        self.assertEqual(snapshots[1][1], "kept filter")
        self.assertIn("Removed worktree", snapshots[1][2])
        attach.assert_not_called()

    def test_failed_removal_stays_in_the_picker_with_an_error_notice(self):
        self.register()
        with patch.object(worktrees, "pick", side_effect=[(str(self.repo), True, "query"), None]) as picker, \
                patch.object(worktrees, "Tmux", return_value=self.tmux), \
                patch.object(worktrees, "attach_worktree") as attach:
            worktrees.wta_main([])
        self.assertIn("Removal failed", picker.call_args.args[2])
        self.assertTrue(self.repo.exists())
        attach.assert_not_called()

    def test_normal_selection_still_attaches(self):
        self.register()
        with patch.object(worktrees, "pick", return_value=(str(self.tree), False, "query")), \
                patch.object(worktrees, "Tmux", return_value=self.tmux), \
                patch.object(worktrees, "attach_worktree") as attach:
            worktrees.wta_main([])
        self.assertEqual(attach.call_args.args[0], str(self.tree))
        self.assertEqual(attach.call_args.args[1], None)
        self.assertIs(attach.call_args.args[3], self.tmux)
        self.assertEqual(attach.call_args.kwargs, {"fresh": False})

    def test_ctrl_x_is_an_explicit_single_selection_action(self):
        rows = [{"path": "/repo", "repo": "example", "branch": "topic", "agent": None,
                 "session_name": "", "running": False}]
        result = subprocess.CompletedProcess([], 0, "query\nctrl-x\n0\texample\n", "")
        with patch.object(worktrees, "require"), patch.object(worktrees.subprocess, "run", return_value=result) as execute:
            self.assertEqual(worktrees.pick(rows, "query"), ("/repo", True, "query"))
        args = execute.call_args.args[0]
        self.assertIn("--no-multi", args)
        self.assertIn("--expect=ctrl-x", args)
        self.assertIn("--print-query", args)

    def test_malformed_action_and_stale_row_index_are_rejected(self):
        for output in ["query\nctrl-x\n-1\trepo\n", "query\nctrl-x\n9\trepo\n", "query\ninvalid\n0\trepo\n"]:
            result = subprocess.CompletedProcess([], 0, output, "")
            with (self.subTest(output=output), patch.object(worktrees, "require"),
                  patch.object(worktrees.subprocess, "run", return_value=result),
                  self.assertRaises(worktrees.WorkspaceError)):
                worktrees.pick([], "query")


def terminal_command(argv, cwd, env, trigger, response):
    pid, descriptor = pty.fork()
    if pid == 0:
        try:
            os.chdir(cwd)
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 60, 160, 0, 0))
            os.execvpe(argv[0], argv, env)
        finally:
            os._exit(127)
    output, status, sent = b"", None, False
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([descriptor], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(descriptor, 65536)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    chunk = b""
                output += chunk
                if trigger in output and not sent:
                    os.write(descriptor, response)
                    sent = True
            finished, result = os.waitpid(pid, os.WNOHANG)
            if finished:
                status = os.waitstatus_to_exitcode(result)
                while select.select([descriptor], [], [], 0)[0]:
                    try:
                        chunk = os.read(descriptor, 65536)
                    except OSError as error:
                        if error.errno != errno.EIO:
                            raise
                        break
                    if not chunk:
                        break
                    output += chunk
                break
        if status is None:
            raise AssertionError("Interactive command did not finish")
        return status, output.decode(errors="replace")
    finally:
        os.close(descriptor)
        if status is None:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)


class TerminalRemovalTests(RepositoryFixture):
    def test_wtrm_confirmation_can_cancel_and_then_remove_without_forcing(self):
        self.registry.remember(worktrees.repository(self.repo), str(self.tree), agent="pi")
        branch = self.git(self.tree, "branch", "--show-current")
        for response in (b"n\n", b"y\n"):
            with self.subTest(response=response):
                code, output = terminal_command([str(BIN / "wtrm"), "--path", str(self.tree)], self.root,
                                                self.env, b"[y/N]", response)
                self.assertEqual(code, 0, output)
                if response == b"n\n":
                    self.assertTrue(self.tree.exists())
                    self.assertIn("cancelled", output)
                else:
                    self.assertFalse(self.tree.exists())
                    self.assertIn("Branch preserved", output)
        self.git(self.repo, "show-ref", "--verify", "refs/heads/" + branch)
        self.assertNotIn(str(self.tree), self.registry.read()["worktrees"])

    def test_wtrm_fails_closed_without_a_controlling_terminal(self):
        result = subprocess.run([str(BIN / "wtrm"), "--path", str(self.tree)], cwd=self.root,
                                env=self.env, capture_output=True, text=True, start_new_session=True,
                                timeout=10, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("controlling terminal", result.stderr)
        self.assertTrue(self.tree.exists())

    @unittest.skipUnless(worktrees.shutil.which("fzf"), "fzf is required")
    def test_real_fzf_ctrl_n_and_ctrl_p_wrap_at_list_boundaries(self):
        rows = [{"path": str(path), "repo": "example", "branch": "topic", "agent": None,
                 "session_name": "", "running": False} for path in (self.repo, self.tree)]
        script = ("import sys,json; sys.dont_write_bytecode=True; "
                  f"sys.path.insert(0,{str(ROOT / 'bin/.local/lib')!r}); "
                  "from worktrees import pick; "
                  f"print('RESULT:'+json.dumps(pick({rows!r},'')),flush=True)")
        env = {**self.env, "TERM": "xterm-256color",
               "FZF_DEFAULT_OPTS": "--no-color --no-unicode --no-mouse --layout=reverse"}
        env.pop("FZF_DEFAULT_OPTS_FILE", None)
        for keys, expected in [(b"\x0e\x0e", self.repo), (b"\x10", self.tree)]:
            with self.subTest(keys=keys):
                code, output = terminal_command([sys.executable, "-c", script], self.root,
                                                env, b"Git status:", keys + b"\r")
                self.assertEqual(code, 0, output)
                result = json.loads(output.split("RESULT:", 1)[1].strip())
                self.assertEqual(result, [str(expected), False, ""])

    @unittest.skipUnless(worktrees.shutil.which("fzf"), "fzf is required")
    def test_real_fzf_distinguishes_enter_from_ctrl_x(self):
        rows = [{"path": str(self.tree), "repo": "example", "branch": "topic", "agent": None,
                 "session_name": "", "running": False}]
        script = ("import sys,json; sys.dont_write_bytecode=True; "
                  f"sys.path.insert(0,{str(ROOT / 'bin/.local/lib')!r}); "
                  "from worktrees import pick; "
                  f"print('RESULT:'+json.dumps(pick({rows!r},'topic')),flush=True)")
        env = {**self.env, "TERM": "xterm-256color", "FZF_DEFAULT_OPTS": "--no-color --no-unicode --no-mouse"}
        env.pop("FZF_DEFAULT_OPTS_FILE", None)
        for key, deleting in [(b"\r", False), (b"\x18", True)]:
            with self.subTest(key=key):
                code, output = terminal_command([sys.executable, "-c", script], self.root,
                                                env, b"Git status:", key)
                self.assertEqual(code, 0, output)
                self.assertIn("Agent:", output)
                self.assertIn("Path:", output)
                result = json.loads(output.split("RESULT:", 1)[1].strip())
                self.assertEqual(result, [str(self.tree), deleting, "topic"])


if __name__ == "__main__":
    unittest.main()
