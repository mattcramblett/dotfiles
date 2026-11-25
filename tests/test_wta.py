import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin/.local/bin"
SPEC = importlib.util.spec_from_file_location("worktrees", ROOT / "bin/.local/lib/worktrees.py")
worktrees = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worktrees)


class RepositoryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wta tests ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env = {**os.environ, "XDG_STATE_HOME": str(self.root / "state"),
                    "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_NOSYSTEM": "1", "TMUX_TMPDIR": str(self.root)}
        self.env.pop("TMUX", None)
        self.env.pop("TMUX_PANE", None)
        self.patch_env = patch.dict(os.environ, self.env, clear=True)
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)
        self.repo = self.make_repo(self.root / "repo")
        self.tree = self.add_tree(self.repo, self.root / "repo-feature", "mattcramblett/feature")
        self.registry = worktrees.Registry()
        self.tmux = Mock(spec=worktrees.Tmux)
        self.tmux.sessions.return_value = []
        self.tmux.value.return_value = ""
        self.tmux.matching.side_effect = lambda path, sessions=None: worktrees.Tmux().matching(path, sessions or [])

    def git(self, directory, *args):
        result = subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def make_repo(self, directory):
        directory.mkdir(parents=True)
        self.git(directory, "init", "-q", "-b", "main")
        self.git(directory, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "initial", "--allow-empty")
        return directory

    def add_tree(self, repo, path, branch):
        self.git(repo, "worktree", "add", "-qb", branch, str(path))
        return path

    def register(self, repo=None):
        self.registry.remember(worktrees.repository(repo or self.repo))

    def cli(self, *args, **env):
        return subprocess.run([str(BIN / "wta"), *args], env={**self.env, **env},
                              cwd=self.root, capture_output=True, text=True)


class DiscoveryTests(RepositoryFixture):
    def test_cross_repo_discovery_and_metadata_refresh(self):
        second = self.make_repo(self.root / "another" / "repo")
        detached = self.root / "detached"
        self.git(second, "worktree", "add", "-q", "--detach", str(detached))
        self.register()
        self.register(second)
        common = worktrees.repository(self.repo)
        self.registry.remember(common, str(self.tree), agent="claude", session_name="SERVEBX-100-fix")
        self.register()
        rows = worktrees.candidates(self.registry, self.tmux)
        self.assertEqual(len(rows), 4)
        selected = next(row for row in rows if row["path"] == str(self.tree))
        self.assertEqual(selected["agent"], "claude")
        self.assertEqual(selected["session_name"], "SERVEBX-100-fix")
        self.assertEqual(next(row for row in rows if row["path"] == str(detached))["branch"], "(detached)")
        self.assertEqual(len({row["repository"] for row in rows}), 2)

    def test_canonical_paths_and_nul_delimited_git_records(self):
        unusual = self.root / "spaces 'quotes' ; $(nope)\tnew\nline"
        self.add_tree(self.repo, unusual, "unusual")
        link = self.root / "linked"
        link.symlink_to(self.repo, target_is_directory=True)
        self.register(link)
        self.register()
        rows = worktrees.candidates(self.registry, self.tmux)
        self.assertEqual(len(rows), 3)
        self.assertIn(str(unusual), [row["path"] for row in rows])
        self.assertEqual(self.registry.read()["repositories"], [str(self.repo / ".git")])

    def test_deleted_worktrees_and_unavailable_repos_are_omitted(self):
        self.register()
        self.registry.remember(str(self.root / "gone" / ".git"))
        shutil.rmtree(self.tree)
        with patch("sys.stderr", new_callable=io.StringIO) as errors:
            rows = worktrees.candidates(self.registry, self.tmux)
        self.assertEqual([row["path"] for row in rows], [str(self.repo)])
        self.assertIn("Skipping", errors.getvalue())
        self.assertTrue((self.repo / ".git/worktrees/repo-feature").exists())

    def test_repositories_sort_reverse_alphabetically_before_running_status_and_recency(self):
        api = self.make_repo(self.root / "api")
        zebra = self.make_repo(self.root / "Zebra")
        recent = self.add_tree(self.repo, self.root / "repo-recent", "recent")
        self.register()
        self.register(zebra)
        self.register(api)
        common = worktrees.repository(self.repo)
        with patch.object(worktrees.time, "time", return_value=100):
            self.registry.remember(common, str(recent))
        with patch.object(worktrees.time, "time", return_value=200):
            self.registry.remember(common, str(self.repo))
        self.tmux.sessions.return_value = [
            {"id": "$1", "path": str(self.tree), "name": "running-task", "activity": 1},
            {"id": "$2", "path": str(zebra), "name": "another-task", "activity": 2},
        ]
        rows = worktrees.candidates(self.registry, self.tmux)
        self.assertEqual([row["repo"] for row in rows], ["Zebra", "repo", "repo", "repo", "api"])
        self.assertEqual([row["path"] for row in rows], list(map(str, [zebra, self.tree, self.repo, recent, api])))

    def test_live_names_are_reconciled_and_running_rows_sort_first(self):
        self.register()
        self.tmux.sessions.return_value = [{"id": "$1", "path": str(self.tree), "name": "renamed", "activity": 1}]
        rows = worktrees.candidates(self.registry, self.tmux)
        self.assertEqual(rows[0]["path"], str(self.tree))
        self.assertEqual(rows[0]["session_name"], "renamed")
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["session_name"], "renamed")

    def test_json_listing_and_individual_registration(self):
        with patch.object(worktrees.Tmux, "sessions", return_value=[]), patch("sys.stdout", new_callable=io.StringIO) as stdout:
            worktrees.wta_main(["--register", str(self.tree)])
            stdout.seek(0)
            stdout.truncate()
            worktrees.wta_main(["--list"])
        self.assertEqual(len(json.loads(stdout.getvalue())), 2)

    def test_json_listing_needs_neither_fzf_nor_tmux(self):
        self.register()
        with patch.object(worktrees.shutil, "which", side_effect=lambda name: None if name in ("fzf", "tmux") else "/git"), patch("sys.stdout", new_callable=io.StringIO) as stdout:
            worktrees.wta_main(["--list"])
        self.assertEqual(len(json.loads(stdout.getvalue())), 2)

    def test_cancelled_picker_does_not_create_workspace(self):
        self.register()
        with patch.object(worktrees.Tmux, "sessions", return_value=[]), patch.object(worktrees, "pick", return_value=None), patch.object(worktrees, "attach_worktree") as attach:
            worktrees.wta_main(["task"])
        attach.assert_not_called()

    def test_registration_via_stow_style_symlinks(self):
        linked = self.root / "links"
        linked.mkdir()
        (linked / "wta").symlink_to(BIN / "wta")
        result = subprocess.run([str(linked / "wta"), "--register", str(self.repo)],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.repo / ".git"), self.registry.read()["repositories"])

    @unittest.skipUnless(shutil.which("stow"), "stow is not installed")
    def test_commands_and_library_work_after_stowing_bin(self):
        home = self.root / "stow-home"
        home.mkdir()
        result = subprocess.run(["stow", "--dir", str(ROOT), "--target", str(home), "bin"],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((home / ".local/lib/worktrees.py").exists())
        for command, args in [("wta", ["--register", str(self.repo)]),
                              ("wt-workspace", ["remember-agent", "pi", "--path", str(self.tree)])]:
            result = subprocess.run([str(home / ".local/bin" / command), *args],
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["agent"], "pi")

    def test_empty_picker_and_invalid_arguments(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--register", result.stderr)
        for args in [("--path", str(self.root)), ("--agent", "pi;bad"),
                     ("--path", ""), ("--register", ""),
                     ("--list", "query"), ("--list", "--agent", "pi"), ("--list", "--fresh")]:
            with self.subTest(args=args):
                self.assertNotEqual(self.cli(*args).returncode, 0)


class RegistryTests(RepositoryFixture):
    def test_concurrent_updates_do_not_lose_records(self):
        processes = [subprocess.Popen([str(BIN / "wt-workspace"), "remember-agent", "pi", "--path", str(path)],
                                      env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for path in (self.repo, self.tree) for _ in range(6)]
        for process in processes:
            _, errors = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, errors.decode())
        data = self.registry.read()
        self.assertEqual(set(data["worktrees"]), {str(self.repo), str(self.tree)})
        self.assertEqual(data["repositories"], [str(self.repo / ".git")])

    def test_malformed_state_is_preserved(self):
        self.registry.directory.mkdir(parents=True)
        self.registry.path.write_text("not json")
        with self.assertRaises(worktrees.WorkspaceError):
            self.register()
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(worktrees.candidates(self.registry, self.tmux), [])
        self.assertEqual(self.registry.path.read_text(), "not json")

    def test_invalid_records_are_ignored_without_being_deleted(self):
        self.register()
        data = self.registry.read()
        data["worktrees"][str(self.tree)] = {"agent": "pi; echo unsafe"}
        self.registry.path.write_text(json.dumps(data))
        with patch("sys.stderr", new_callable=io.StringIO):
            rows = worktrees.candidates(self.registry, self.tmux)
        self.assertIsNone(next(row for row in rows if row["path"] == str(self.tree))["agent"])
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)], {"agent": "pi; echo unsafe"})

    def test_unwritable_state_does_not_block_attachment(self):
        self.registry.directory.parent.mkdir(parents=True)
        self.registry.directory.write_text("not a directory")
        self.tmux.sessions.return_value = [{"id": "$9", "path": str(self.tree), "name": "existing", "activity": 1}]
        with patch("sys.stderr", new_callable=io.StringIO):
            worktrees.attach_worktree(str(self.tree), "claude", self.registry, self.tmux)
        self.tmux.attach.assert_called_once_with("$9")


class AttachmentTests(RepositoryFixture):
    def test_existing_workspace_is_reused_and_override_only_changes_preference(self):
        self.register()
        self.tmux.sessions.return_value = [{"id": "$9", "path": str(self.tree), "name": "existing", "activity": 1}]
        with patch.object(worktrees, "create_workspace") as create:
            worktrees.attach_worktree(str(self.tree), "claude", self.registry, self.tmux)
        create.assert_not_called()
        self.tmux.attach.assert_called_once_with("$9")
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["agent"], "claude")

    def test_new_workspace_uses_saved_name_and_agent(self):
        self.registry.remember(worktrees.repository(self.repo), str(self.tree), agent="pi", session_name="task-name")
        with patch.object(worktrees, "create_workspace", return_value="$5") as create:
            worktrees.attach_worktree(str(self.tree), None, self.registry, self.tmux)
        create.assert_called_once_with(self.tmux, self.registry, str(self.tree), "task-name", layout=True, agent="pi", fresh=False)
        self.tmux.attach.assert_called_once_with("$5")

    def test_collision_uses_path_hash_and_never_reuses_other_worktree(self):
        self.registry.remember(worktrees.repository(self.repo), str(self.tree), session_name="task-name")
        self.tmux.sessions.return_value = [{"id": "$9", "path": str(self.repo), "name": "task-name", "activity": 1}]
        with patch.object(worktrees, "create_workspace", return_value="$5") as create:
            worktrees.attach_worktree(str(self.tree), None, self.registry, self.tmux)
        name = create.call_args.args[3]
        self.assertRegex(name, r"^task-name-[0-9a-f]{8}$")
        self.tmux.attach.assert_called_once_with("$5")

    def test_default_name_respects_branch_prefix_and_detached_fallback(self):
        common = worktrees.repository(self.repo)
        self.assertEqual(worktrees.default_name(str(self.tree), common), "repo-feature")
        self.git(self.repo, "config", "worktree.branchPrefix", "matt")
        self.assertEqual(worktrees.default_name(str(self.tree), common), "repo-cramblett-feature")
        self.git(self.tree, "checkout", "--detach", "-q")
        self.assertEqual(worktrees.default_name(str(self.tree), common), "repo-repo-feature")

    def test_matching_uses_worktree_identity_and_most_recent_session(self):
        sessions = [{"id": "$1", "path": str(self.tree), "activity": 1},
                    {"id": "$2", "path": str(self.tree), "activity": 3},
                    {"id": "$3", "path": str(self.repo), "activity": 5}]
        self.assertEqual(worktrees.Tmux().matching(str(self.tree), sessions)["id"], "$2")

    def test_attach_selects_client_action(self):
        tmux = worktrees.Tmux()
        with patch.dict(os.environ, {"TMUX": "test"}), patch.object(tmux, "call") as call:
            tmux.attach("$1")
        call.assert_called_once_with("switch-client", "-t", "$1")
        with patch.dict(os.environ, {}, clear=True), patch.object(worktrees.subprocess, "run") as execute:
            execute.return_value.returncode = 0
            tmux.attach("$1")
        execute.assert_called_once_with(["tmux", "attach-session", "-t", "$1"])

    def test_missing_editor_fails_before_session_creation(self):
        with patch.object(worktrees.shutil, "which", side_effect=lambda name: None if name == "nvim" else "/bin/true"):
            with self.assertRaisesRegex(worktrees.WorkspaceError, "nvim"):
                worktrees.create_workspace(self.tmux, self.registry, str(self.tree), "test", layout=True)
        self.tmux.call.assert_not_called()

    def test_shared_layout_rejects_ambiguous_move_targets(self):
        for pane in ("", "main:1", "=session"):
            with self.subTest(pane=pane), self.assertRaisesRegex(worktrees.WorkspaceError, "exact tmux pane"):
                worktrees.create_workspace(self.tmux, self.registry, str(self.tree), "test", move_pane=pane)
        self.tmux.call.assert_not_called()

    def test_direct_attach_survives_malformed_registry(self):
        self.registry.directory.mkdir(parents=True)
        self.registry.path.write_text("bad")
        self.tmux.sessions.return_value = [{"id": "$9", "path": str(self.tree), "name": "existing", "activity": 1}]
        with patch("sys.stderr", new_callable=io.StringIO):
            worktrees.attach_worktree(str(self.tree), None, self.registry, self.tmux)
        self.tmux.attach.assert_called_once_with("$9")
        self.assertEqual(self.registry.path.read_text(), "bad")


class AgentTrackingTests(RepositoryFixture):
    def test_moved_pane_identity_wins_over_original_launch_directory(self):
        self.tmux.value.return_value = str(self.tree)
        with patch.dict(os.environ, {"TMUX_PANE": "%7"}), patch.object(worktrees.os, "getcwd", return_value=str(self.repo)):
            worktrees.remember_agent(self.tmux, self.registry, "pi")
        self.assertEqual(set(self.registry.read()["worktrees"]), {str(self.tree)})
        self.tmux.call.assert_any_call("set-option", "-p", "-t", "%7", "@worktree_agent", "pi")
        self.tmux.call.assert_any_call("set-option", "-p", "-u", "-t", "%7", "@worktree_conversation")
        worktrees.remember_agent(self.tmux, self.registry, "claude", path=str(self.tree))
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["agent"], "claude")

    def test_outside_git_is_noop_and_agent_names_are_validated(self):
        with patch.object(worktrees.os, "getcwd", return_value=str(self.root)):
            worktrees.remember_agent(self.tmux, self.registry, "pi")
        self.assertFalse(self.registry.path.exists())
        for name in ("pi --resume", "$(bad)", "../pi", "-bad", ""):
            with self.subTest(name=name), self.assertRaises(worktrees.WorkspaceError):
                worktrees.remember_agent(self.tmux, self.registry, name)


class PickerTests(unittest.TestCase):
    def test_picker_enables_cyclic_navigation(self):
        result = subprocess.CompletedProcess([], 130, "", "")
        with patch.object(worktrees, "require"), patch.object(worktrees.subprocess, "run", return_value=result) as execute:
            self.assertIsNone(worktrees.pick([], ""))
        self.assertIn("--cycle", execute.call_args.args[0])

    def test_query_safe_preview_and_selection(self):
        rows = [{"path": "/repo/'; touch nope", "repo": "repo", "branch": "branch", "agent": "pi",
                 "session_name": "task", "running": False}]
        result = subprocess.CompletedProcess([], 0, "kept query\n\n0\trepo\n", "")
        with patch.object(worktrees, "require"), patch.object(worktrees.subprocess, "run", return_value=result) as execute:
            self.assertEqual(worktrees.pick(rows, "SERVEBX-100"), (rows[0]["path"], False, "kept query"))
        args = execute.call_args.args[0]
        self.assertEqual(args[args.index("--query") + 1], "SERVEBX-100")
        preview = args[args.index("--preview") + 1]
        self.assertNotIn(rows[0]["path"], preview)
        self.assertTrue(preview.endswith(" {1}"))

    def test_compact_rows_keep_three_visible_columns_and_full_preview_metadata(self):
        rows = [{"path": "/example/first", "repo": "repo-one", "branch": "feature/full-branch", "agent": "example-agent",
                 "session_name": "named-task", "running": True},
                {"path": "/example/second", "repo": "repo-two", "branch": "topic", "agent": None,
                 "session_name": "", "running": False}]

        def select(argv, **kwargs):
            fields = [line.split("\t") for line in kwargs["input"].splitlines()]
            self.assertEqual(fields, [["0", "repo-one  named-task     running"],
                                      ["1", "repo-two  topic          stopped"]])
            self.assertIn("--with-nth=2..", argv)
            self.assertEqual(argv[argv.index("--header") + 1].splitlines()[0], "REPO      TASK / BRANCH  STATUS")
            preview = shlex.split(argv[argv.index("--preview") + 1])
            with open(preview[-2]) as stream:
                self.assertEqual(json.load(stream), rows)
            return subprocess.CompletedProcess(argv, 0, "query\nctrl-x\n1\trepo-two\ttopic\tstopped\n", "")

        with patch.object(worktrees, "require"), patch.object(worktrees.subprocess, "run", side_effect=select):
            self.assertEqual(worktrees.pick(rows, "query"), (rows[1]["path"], True, "query"))

    def test_columns_align_with_header_for_different_label_lengths(self):
        rows = [{"path": "/example/first", "repo": "api", "branch": "unused", "session_name": "fix",
                 "running": True},
                {"path": "/example/second", "repo": "long-repository-name", "branch": "feature/long-branch-name",
                 "session_name": "", "running": False},
                {"path": "/example/third", "repo": "web\tclient", "branch": "unused", "session_name": "task\n\u754c",
                 "running": True}]
        result = subprocess.CompletedProcess([], 0, "query\n\n2\tselected row\n", "")
        with patch.object(worktrees, "require"), patch.object(worktrees.subprocess, "run", return_value=result) as execute:
            self.assertEqual(worktrees.pick(rows, "query", "Removed\nworktree"), (rows[2]["path"], False, "query"))
        args = execute.call_args.args[0]
        header, hint, notice = args[args.index("--header") + 1].splitlines()
        lines = execute.call_args.kwargs["input"].splitlines()
        self.assertEqual(len(lines), len(rows))
        self.assertEqual(hint, "Ctrl-X removes the worktree and tagged sessions")
        self.assertEqual(notice, "Removed\\nworktree")
        for index, (line, row) in enumerate(zip(lines, rows)):
            with self.subTest(index=index):
                hidden_index, visible = line.split("\t")
                self.assertEqual(hidden_index, str(index))
                repo = worktrees.display(row["repo"])
                task = worktrees.display(row["session_name"] or row["branch"])
                status = "running" if row["running"] else "stopped"
                self.assertEqual(visible[:len(repo)], repo)
                self.assertEqual(visible[header.index("TASK / BRANCH"):header.index("STATUS")].rstrip(), task)
                self.assertEqual(visible[header.index("STATUS"):], status)

    def test_empty_picker_uses_header_widths(self):
        result = subprocess.CompletedProcess([], 130, "", "")
        with patch.object(worktrees, "require"), patch.object(worktrees.subprocess, "run", return_value=result) as execute:
            self.assertIsNone(worktrees.pick([], ""))
        args = execute.call_args.args[0]
        self.assertEqual(args[args.index("--header") + 1].splitlines()[0], "REPO  TASK / BRANCH  STATUS")

    def test_preview_shows_full_details_without_interpreting_terminal_controls(self):
        row = {"branch": "feature/full-branch", "agent": "example-agent", "path": "/repo/quote'; $(nope)\nline"}
        with patch("sys.stdout", new_callable=io.StringIO) as stdout, patch.object(worktrees.subprocess, "run") as execute:
            worktrees.preview_worktree(row)
        self.assertIn("Branch: feature/full-branch", stdout.getvalue())
        self.assertIn("Agent: example-agent", stdout.getvalue())
        self.assertIn("Path: /repo/quote'; $(nope)\\nline", stdout.getvalue())
        self.assertNotIn(row["path"], stdout.getvalue())
        self.assertIn("Git status:", stdout.getvalue())
        execute.assert_called_once_with(["git", "-C", row["path"], "status", "--short", "--branch"], check=False)

    def test_preview_handles_an_unknown_agent(self):
        with patch("sys.stdout", new_callable=io.StringIO) as stdout, patch.object(worktrees.subprocess, "run"):
            worktrees.preview_worktree({"branch": "topic", "agent": None, "path": "/repo"})
        self.assertIn("Agent: (unknown)", stdout.getvalue())

    def test_cancel_and_bad_selection(self):
        with patch.object(worktrees, "require"), patch.object(worktrees.subprocess, "run") as execute:
            for code in (1, 130):
                execute.return_value = subprocess.CompletedProcess([], code, "", "")
                self.assertIsNone(worktrees.pick([], ""))
            for value in ("-1", "2", "bad"):
                execute.return_value = subprocess.CompletedProcess([], 0, value, "")
                with self.assertRaises(worktrees.WorkspaceError):
                    worktrees.pick([], "")


class PreviewTests(RepositoryFixture):
    def test_preview_command_prints_metadata_then_real_git_status(self):
        snapshot = self.root / "picker-snapshot.json"
        row = {"branch": "feature/preview-case", "agent": "example-agent", "path": str(self.tree)}
        snapshot.write_text(json.dumps([row]))
        result = subprocess.run([str(BIN / "wt-workspace"), "preview", str(snapshot), "0"],
                                cwd=self.root, env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Branch: feature/preview-case", result.stdout)
        self.assertIn("Agent: example-agent", result.stdout)
        self.assertIn("Path: " + str(self.tree), result.stdout)
        self.assertLess(result.stdout.index("Git status:"), result.stdout.index("## "))


if __name__ == "__main__":
    unittest.main()
