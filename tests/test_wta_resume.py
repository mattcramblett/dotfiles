import io
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch
import unittest

from test_wta import BIN, RepositoryFixture, worktrees


CLAUDE_ID = "c167920c-e037-43c0-b1bd-33a5eb65a287"


class ConversationTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.session = self.root / "session 'quoted'; $(ignored).jsonl"
        self.session.write_text(json.dumps({"type": "session", "id": "pi-session", "cwd": str(self.repo)}) + "\n")
        self.conversation = {"agent": "pi", "session_id": "pi-session",
                             "session_file": str(self.session), "cwd": str(self.repo)}

    def remember(self, conversation=None):
        self.registry.remember(worktrees.repository(self.repo), str(self.tree), agent="pi",
                               conversation=self.conversation if conversation is None else conversation)

    def test_captures_exact_conversation_in_the_tagged_worktree(self):
        self.tmux.value.return_value = str(self.tree)
        worktrees.remember_conversation(self.tmux, self.registry, "pi", str(self.repo), "pi-session", str(self.session), pane="%7")
        record = self.registry.read()["worktrees"][str(self.tree)]
        self.assertEqual(record["conversation"], self.conversation)
        option = next(call.args[-1] for call in self.tmux.call.call_args_list if "@worktree_conversation" in call.args)
        self.assertEqual(json.loads(option), self.conversation)
        self.assertNotIn(str(self.repo), self.registry.read()["worktrees"])

    def test_a_conversation_moves_between_worktrees_without_leaving_a_duplicate_resume_target(self):
        common = worktrees.repository(self.repo)
        self.registry.remember(common, str(self.repo), agent="pi", conversation=self.conversation)
        self.remember()
        records = self.registry.read()["worktrees"]
        self.assertIsNone(records[str(self.repo)]["conversation"])
        self.assertEqual(records[str(self.tree)]["conversation"], self.conversation)
        self.assertEqual(records[str(self.repo)]["agent"], "pi")

    def test_captures_pane_metadata_even_before_entering_a_repository(self):
        worktrees.remember_conversation(self.tmux, self.registry, "pi", str(self.root), "pi-session", str(self.session), pane="%7")
        self.tmux.call.assert_any_call("set-option", "-p", "-t", "%7", "@worktree_agent", "pi")
        self.assertTrue(any("@worktree_conversation" in call.args for call in self.tmux.call.call_args_list))
        self.assertFalse(self.registry.path.exists())

    def test_new_launch_and_ephemeral_sessions_clear_old_references(self):
        self.remember()
        worktrees.remember_agent(self.tmux, self.registry, "pi", path=str(self.tree))
        self.assertIsNone(self.registry.read()["worktrees"][str(self.tree)]["conversation"])
        self.remember()
        worktrees.remember_conversation(self.tmux, self.registry, "pi", str(self.repo), "ephemeral", path=str(self.tree))
        self.assertIsNone(self.registry.read()["worktrees"][str(self.tree)]["conversation"])

    def test_agent_override_cannot_reuse_another_agents_conversation(self):
        self.remember()
        common = worktrees.repository(self.repo)
        self.registry.remember(common, str(self.tree), agent="pi")
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["conversation"], self.conversation)
        self.registry.remember(common, str(self.tree), agent="claude")
        self.assertIsNone(self.registry.read()["worktrees"][str(self.tree)]["conversation"])

    def test_pi_resume_uses_exact_file_and_original_working_directory(self):
        cwd, arguments = worktrees.resume_target("pi", self.conversation)
        self.assertEqual(cwd, str(self.repo))
        self.assertEqual(arguments, ["--session", str(self.session)])

    def test_claude_resume_uses_exact_uuid(self):
        conversation = {**self.conversation, "agent": "claude", "session_id": CLAUDE_ID}
        self.assertEqual(worktrees.resume_target("claude", conversation), (str(self.repo), ["--resume", CLAUDE_ID]))

    def test_missing_stale_and_invalid_pi_sessions_fall_back(self):
        for content in ("bad json", "[]", json.dumps({"type": "session", "id": "wrong", "cwd": str(self.repo)})):
            with self.subTest(content=content), patch("sys.stderr", new_callable=io.StringIO) as errors:
                self.session.write_text(content)
                self.assertEqual(worktrees.resume_target("pi", self.conversation), (None, []))
                self.assertIn("starting a new conversation", errors.getvalue())
        self.session.unlink()
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(worktrees.resume_target("pi", self.conversation), (None, []))
            self.assertEqual(worktrees.resume_target("pi", {**self.conversation, "cwd": str(self.root / "missing")}), (None, []))

    def test_invalid_conversation_does_not_hide_the_agent_or_workspace(self):
        self.remember({**self.conversation, "session_id": "--bad"})
        data = self.registry.read()
        with patch("sys.stderr", new_callable=io.StringIO):
            record = worktrees.preferences(data, str(self.tree), worktrees.repository(self.repo))
        self.assertEqual(record["agent"], "pi")
        self.assertIsNone(record["conversation"])
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["conversation"]["session_id"], "--bad")

    def test_no_resume_for_legacy_or_other_agent_records(self):
        self.assertEqual(worktrees.resume_target("pi", None), (None, []))
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(worktrees.resume_target("claude", self.conversation), (None, []))
            self.assertEqual(worktrees.resume_target("claude", {**self.conversation, "agent": "claude", "session_id": "not-uuid"}), (None, []))

    def test_hook_capture_and_subagent_filtering(self):
        payload = {"hook_event_name": "SessionStart", "cwd": str(self.tree),
                   "session_id": CLAUDE_ID, "transcript_path": str(self.session)}
        worktrees.record_hook(self.tmux, self.registry, "claude", payload)
        record = self.registry.read()["worktrees"][str(self.tree)]
        self.assertEqual(record["conversation"]["session_id"], CLAUDE_ID)
        for extra in ({"agent_id": "subagent"}, {"subagent_id": "worker"}, {"hook_event_name": "PostToolUse"}):
            worktrees.record_hook(self.tmux, self.registry, "claude", {**payload, **extra, "session_id": "invalid"})
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)], record)

    def test_hook_keeps_the_original_directory_after_in_session_directory_changes(self):
        conversation = {**self.conversation, "agent": "claude", "session_id": CLAUDE_ID}
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": str(self.tree),
                   "session_id": CLAUDE_ID, "transcript_path": str(self.session)}
        self.tmux.value.side_effect = lambda pane, expression: (json.dumps(conversation)
                                                              if expression == "#{@worktree_conversation}" else str(self.tree))
        with patch.dict(os.environ, {"TMUX_PANE": "%7"}):
            worktrees.record_hook(self.tmux, self.registry, "claude", payload)
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["conversation"]["cwd"], str(self.repo))

    def test_session_header_accepts_equivalent_canonical_directories(self):
        alias = self.root / "repo-link"
        alias.symlink_to(self.repo, target_is_directory=True)
        self.session.write_text(json.dumps({"type": "session", "id": "pi-session", "cwd": str(alias)}))
        self.assertEqual(worktrees.resume_target("pi", self.conversation)[0], str(self.repo))

    def test_recording_cli_preserves_arguments_and_emits_no_context(self):
        result = subprocess.run([str(BIN / "wt-workspace"), "remember-conversation", "pi", "--cwd", str(self.repo),
                                 "--session-id", "pi-session", "--session-file", str(self.session), "--path", str(self.tree)],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["conversation"], self.conversation)

    def test_launcher_passes_references_as_arguments_not_shell_code(self):
        self.remember()
        with patch.object(worktrees.os, "getcwd", return_value=str(self.tree)), patch.object(worktrees.os, "execvp") as execute:
            worktrees.agent_shell("pi", self.registry)
        arguments = execute.call_args.args[1]
        self.assertEqual(arguments[4:], ["pi", str(self.tree), str(self.repo), "--session", str(self.session)])
        self.assertNotIn(str(self.session), arguments[2])

    def test_fresh_launcher_skips_the_saved_conversation(self):
        self.remember()
        with patch.object(worktrees.os, "getcwd", return_value=str(self.tree)), patch.object(worktrees.os, "execvp") as execute:
            worktrees.agent_shell("pi", self.registry, fresh=True)
        self.assertEqual(execute.call_args.args[1][4:], ["pi", str(self.tree), str(self.tree)])

    def test_fresh_flag_reaches_creation_and_does_not_replace_existing_sessions(self):
        with patch.object(worktrees, "create_workspace", return_value="$1") as create:
            worktrees.attach_worktree(str(self.tree), "pi", self.registry, self.tmux, fresh=True)
        self.assertTrue(create.call_args.kwargs["fresh"])
        self.tmux.sessions.return_value = [{"id": "$2", "path": str(self.tree), "name": "existing", "activity": 1}]
        with patch.object(worktrees, "create_workspace") as create:
            worktrees.attach_worktree(str(self.tree), "pi", self.registry, self.tmux, fresh=True)
        create.assert_not_called()
        self.tmux.attach.assert_called_with("$2")


if __name__ == "__main__":
    unittest.main()
