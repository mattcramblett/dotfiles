import importlib.util
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("worktree_setup", ROOT / "bin/.local/lib/worktree_setup.py")
setup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = setup
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wt setup ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.source = self.base / "repo"
        self.root = self.base / "repo-feature"
        self.common = self.source / ".git"
        self.common.mkdir(parents=True)
        self.root.mkdir()
        self.files = {self.root: set(), self.source: set()}
        self.calls = []
        self.versions = {"yarn": "4.0.0", "npm": "10.0.0", "pnpm": "9.0.0", "corepack": "0.35.0"}
        self.exits = {}
        self.linker = "node-modules"
        self.frozen = "frozen=true"
        self.clean = ""
        for target, replacement in [("git", self.git), ("run", self.fake_run)]:
            patcher = patch.object(setup, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in [patch.object(setup.platform, "system", return_value="Linux"),
                        patch.object(setup.shutil, "which", return_value=None),
                        patch.dict(os.environ, {}, clear=True),
                        patch("sys.stdout", new_callable=io.StringIO),
                        patch("sys.stderr", new_callable=io.StringIO)]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, name, contents="", source=False, tracked=True):
        root = self.source if source else self.root
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        if tracked:
            self.files[root].add(name)
        return path

    def node(self, path=".", manager="yarn", version=None, source=False):
        prefix = "" if path == "." else path + "/"
        manifest = {} if not version else {"packageManager": f"{manager}@{version}"}
        self.write(prefix + "package.json", json.dumps(manifest), source)
        self.write(prefix + setup.LOCKS[manager][-1], "locked", source)

    def ruby(self, path=".", source=False):
        prefix = "" if path == "." else path + "/"
        self.write(prefix + "Gemfile", "source 'https://rubygems.org'\n", source)
        self.write(prefix + "Gemfile.lock", "BUNDLED WITH\n   2.7.2\n", source)

    def git(self, path, *args):
        path = Path(path)
        if args == ("rev-parse", "--show-toplevel"):
            return str(self.root) + "\n"
        if args == ("rev-parse", "--path-format=absolute", "--git-common-dir"):
            return str(self.common) + "\n"
        if args == ("ls-files", "-z"):
            return "\0".join(sorted(self.files[path])) + "\0"
        self.fail(f"Unexpected Git command: {args}")

    def fake_run(self, argv, cwd, env=None, capture=False, check=True):
        argv = list(argv)
        self.calls.append((argv, Path(cwd), dict(env) if env is not None else None))
        key = tuple(argv)
        code = self.exits.get(key, 0)
        output = ""
        if argv[0] == "/bin/cp":
            destination = Path(argv[-1])
            for source in map(Path, argv[3:-1]):
                target = destination / source.name if destination.is_dir() else destination
                if source.is_dir() and not source.is_symlink():
                    shutil.copytree(source, target, symlinks=True)
                else:
                    shutil.copy2(source, target, follow_symlinks=False)
        elif argv[-1] == "--version" and argv[0] != "bundle":
            output = self.versions[argv[-2]] + "\n"
        elif argv[-3:] == ["config", "get", "nodeLinker"]:
            output = self.linker + "\n"
        elif argv[0] == "node":
            output = '["v22.0.0","darwin","arm64","127"]\n'
        elif argv[0] == "bundle" and "config" in argv:
            output = (self.clean if "clean" in argv else self.frozen) + "\n"
        result = subprocess.CompletedProcess(argv, code, output, "")
        if check and code:
            raise setup.SetupError(f"{argv[0]} failed")
        return result

    def configure(self, projects):
        (self.common / "worktree-setup.json").write_text(json.dumps({"projects": projects}))

    def execute(self, reuse=True):
        setup.setup(self.root, reuse=reuse)

    def commands(self, executable):
        return [call for call in self.calls if call[0][0] == executable]

    def test_relative_worktree_path_is_resolved_before_git_queries(self):
        self.node(manager="npm")
        with patch.object(setup, "git", side_effect=self.git) as queries, chdir(self.base):
            setup.setup(Path(self.root.name), reuse=False)
        self.assertTrue(all(call.args[0].is_absolute() for call in queries.call_args_list))
        self.assertEqual(self.commands("npm")[-1][1], self.root)

    def test_mixed_ruby_and_independent_nested_node_roots(self):
        self.ruby()
        self.node("client", "yarn")
        self.node("tools", "npm")
        self.node("docs", "pnpm")
        self.execute()
        self.assertEqual(self.commands("bundle")[-1][0], ["bundle", "_2.7.2_", "exec", "ruby", "-e", "exit"])
        for command, path in [("yarn", "client"), ("npm", "tools"), ("pnpm", "docs")]:
            self.assertEqual(self.commands(command)[-1][1], self.root / path)
        self.assertEqual(self.commands("yarn")[-1][0], ["yarn", "install", "--immutable"])
        self.assertEqual(self.commands("npm")[-1][0], ["npm", "ci"])
        self.assertEqual(self.commands("pnpm")[-1][0], ["pnpm", "install", "--frozen-lockfile"])

    def test_runtime_install_precedes_dependencies_and_deduplicates_parent(self):
        self.write(".tool-versions", "ruby 3.4.0\nnodejs 22.0.0\n")
        self.ruby()
        self.node("client")
        self.node("other", "npm")
        self.write("client/.tool-versions", "nodejs 20.0.0\n")
        self.execute()
        self.assertEqual([(c[0], c[1]) for c in self.commands("asdf")],
                         [(["asdf", "install"], self.root),
                          (["asdf", "install"], self.root / "client")])
        self.assertEqual(self.calls[0][0], ["asdf", "install"])

    def test_nested_runtime_files_inherit_each_tool_and_override_shell_versions(self):
        self.ruby("tools/client")
        self.write(".tool-versions", "ruby 3.3.0\nnodejs 20.0.0\n")
        self.write("tools/.tool-versions", "ruby 3.4.0\n")
        self.write("tools/client/.tool-versions", "nodejs 22.0.0\n")
        with patch.dict(os.environ, {"ASDF_RUBY_VERSION": "3.2.0", "ASDF_NODEJS_VERSION": "18.0.0"}):
            self.execute()
        self.assertEqual([c[1] for c in self.commands("asdf")],
                         [self.root, self.root / "tools", self.root / "tools/client"])
        env = self.commands("bundle")[-1][2]
        self.assertEqual(env["ASDF_RUBY_VERSION"], "3.4.0")
        self.assertEqual(env["ASDF_NODEJS_VERSION"], "22.0.0")

    def test_exact_legacy_version_files_without_tool_versions(self):
        self.ruby()
        self.node("client", "npm")
        self.write(".ruby-version", "ruby-3.4.0\n")
        self.write("client/.nvmrc", "v22.0.0\n")
        self.execute()
        args = [c[0] for c in self.commands("asdf")]
        self.assertIn(["asdf", "install", "ruby", "3.4.0"], args)
        self.assertIn(["asdf", "install", "nodejs", "22.0.0"], args)
        self.assertEqual(self.commands("bundle")[-1][2]["ASDF_RUBY_VERSION"], "3.4.0")
        self.assertEqual(self.commands("npm")[-1][2]["ASDF_NODEJS_VERSION"], "22.0.0")

    def test_nonexact_legacy_runtime_fails_before_install(self):
        self.ruby()
        self.write(".ruby-version", "3.4\n")
        with self.assertRaisesRegex(setup.SetupError, "exact runtime version"):
            self.execute()
        self.assertEqual(self.calls, [])

    def test_package_manager_pin_is_verified(self):
        self.node(version="4.1.0")
        with self.assertRaisesRegex(setup.SetupError, "4.1.0 required"):
            self.execute()
        self.assertEqual([c[0] for c in self.calls], [["yarn", "--version"]])

    def test_corepack_dispatch_honors_project_version(self):
        self.node(version="4.0.0")
        with patch.object(setup.shutil, "which", return_value="/bin/corepack"):
            self.execute()
        self.assertEqual(self.calls[-1][0], ["corepack", "yarn", "install", "--immutable"])

    def test_unavailable_corepack_shim_falls_back_to_installed_manager(self):
        self.node(version="4.0.0")
        self.exits[("corepack", "--version")] = 1
        with patch.object(setup.shutil, "which", return_value="/bin/corepack"):
            self.execute()
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])

    def test_classic_yarn_uses_frozen_lockfile_without_seeding(self):
        self.node(version="1.22.22")
        self.versions["yarn"] = "1.22.22"
        self.execute()
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--frozen-lockfile"])
        self.assertEqual(self.commands("/bin/cp"), [])

    def test_ambiguous_lockfiles_fail_without_declared_manager(self):
        self.node()
        self.write("package-lock.json", "{}")
        with self.assertRaisesRegex(setup.SetupError, "Cannot choose"):
            self.execute()
        self.assertEqual(self.calls, [])

    def test_declared_manager_selects_one_lockfile(self):
        self.node(version="4.0.0")
        self.write("package-lock.json", "{}")
        self.execute()
        self.assertEqual(self.calls[-1][0][0], "yarn")
        self.assertEqual(len([c for c in self.calls if "install" in c[0]]), 1)

    def test_shrinkwrap_and_package_lock_are_one_npm_project(self):
        self.node(manager="npm")
        self.write("npm-shrinkwrap.json", "{}")
        self.execute()
        self.assertEqual(self.calls[-1][0], ["npm", "ci"])
        self.assertEqual(len(self.commands("npm")), 2)

    def test_workspace_manifests_without_locks_are_not_separate_installs(self):
        self.node()
        self.write("apps/site/package.json", "{}")
        self.write("docs/example/yarn.lock", "fixture")
        self.execute()
        self.assertEqual(len(self.commands("yarn")), 2)
        self.assertEqual(self.calls[-1][1], self.root)

    def test_untracked_projects_and_environment_files_are_ignored(self):
        self.write("package.json", "{}", tracked=False)
        self.write("package-lock.json", "{}", tracked=False)
        self.write(".env.local", "EXAMPLE=synthetic", tracked=False)
        self.execute()
        self.assertEqual(self.calls, [])
        self.assertEqual((self.root / ".env.local").read_text(), "EXAMPLE=synthetic")

    def test_config_can_select_workspaces_and_custom_setup(self):
        self.node()
        self.node("e2e", "npm")
        self.configure([{"path": ".", "type": "node", "workspaces": ["example-root", "example-app"]},
                        {"path": ".", "type": "command", "command": ["bootstrap", "argument with spaces"]}])
        self.execute()
        yarn = self.commands("yarn")[-1]
        self.assertEqual(yarn[0], ["yarn", "workspaces", "focus", "example-root", "example-app"])
        self.assertEqual(yarn[2]["YARN_ENABLE_IMMUTABLE_INSTALLS"], "true")
        self.assertEqual(self.calls[-1][0], ["bootstrap", "argument with spaces"])
        self.assertEqual(self.commands("npm"), [])

    def test_config_can_disable_dependency_setup(self):
        self.node()
        self.write(".tool-versions", "nodejs 22.0.0")
        self.configure([])
        self.execute()
        self.assertEqual([c[0] for c in self.calls], [["asdf", "install"]])

    def test_invalid_config_fails_before_setup(self):
        for config in [{"project": []}, {"projects": {}}, {"projects": [None]},
                       {"projects": [{"path": "../outside", "type": "node"}]},
                       {"projects": [{"path": "/outside", "type": "node"}]},
                       {"projects": [{"path": ".", "type": "command"}]},
                       {"projects": [{"path": ".", "type": "node", "workspaces": "app"}]}]:
            with self.subTest(config=config):
                (self.common / "worktree-setup.json").write_text(json.dumps(config))
                with self.assertRaises(setup.SetupError):
                    self.execute()
        self.assertEqual(self.calls, [])

    def test_workspace_selection_not_silently_ignored_by_other_managers(self):
        self.node(manager="npm")
        self.configure([{"path": ".", "type": "node", "workspaces": ["app"]}])
        with self.assertRaisesRegex(setup.SetupError, "Yarn 2"):
            self.execute()
        self.assertNotIn(["npm", "ci"], [c[0] for c in self.calls])

    def test_ruby_reuses_installed_gems_without_install(self):
        self.ruby()
        self.execute()
        self.assertEqual(self.commands("gem"), [])
        self.assertNotIn(["bundle", "_2.7.2_", "install"], [c[0] for c in self.calls])
        for argv, cwd, env in self.commands("bundle"):
            if argv[-1] == "check":
                self.assertEqual(env["BUNDLE_FROZEN"], "true")
                self.assertEqual(env["BUNDLE_GEMFILE"], str(self.root / "Gemfile"))

    def test_missing_locked_bundler_and_gems_are_installed(self):
        self.ruby()
        self.exits[("bundle", "_2.7.2_", "--version")] = 1
        self.exits[("bundle", "_2.7.2_", "check")] = 1
        self.execute()
        self.assertEqual(self.commands("gem")[0][0],
                         ["gem", "install", "bundler", "--version", "2.7.2", "--no-document"])
        self.assertIn(["bundle", "_2.7.2_", "install"], [c[0] for c in self.commands("bundle")])
        self.assertEqual(self.commands("bundle")[-1][2]["BUNDLE_FROZEN"], "true")
        self.assertEqual(self.commands("bundle")[-1][2]["BUNDLE_CLEAN"], "false")

    def test_ruby_local_configuration_cannot_disable_frozen_mode(self):
        self.ruby()
        self.frozen = "frozen=false"
        with self.assertRaisesRegex(setup.SetupError, "overrides safe frozen=true"):
            self.execute()
        self.assertFalse(any(c[0][-1] in ("check", "install") for c in self.commands("bundle")))

    def test_ruby_explicit_false_cleanup_setting_is_also_supported(self):
        self.ruby()
        self.clean = "clean=false"
        self.execute()
        self.assertEqual(self.commands("bundle")[-1][0], ["bundle", "_2.7.2_", "exec", "ruby", "-e", "exit"])

    def test_ruby_local_configuration_cannot_enable_gem_cleanup(self):
        self.ruby()
        self.clean = "clean=true"
        with self.assertRaisesRegex(setup.SetupError, "overrides safe clean=false"):
            self.execute()
        self.assertFalse(any(c[0][-1] in ("check", "install") for c in self.commands("bundle")))

    def test_ruby_activation_failure_cannot_be_hidden_by_successful_bundle_check(self):
        self.ruby()
        self.exits[("bundle", "_2.7.2_", "exec", "ruby", "-e", "exit")] = 1
        with self.assertRaises(setup.SetupError):
            self.execute()
        self.assertNotIn(["bundle", "_2.7.2_", "install"], [c[0] for c in self.calls])
        self.assertEqual((self.root / "Gemfile.lock").read_text(), "BUNDLED WITH\n   2.7.2\n")

    def test_ruby_missing_bundler_pin_fails_without_install(self):
        self.ruby()
        self.write("Gemfile.lock", "GEM\n")
        with self.assertRaisesRegex(setup.SetupError, "BUNDLED WITH"):
            self.execute()
        self.assertEqual(self.commands("bundle"), [])

    def test_failure_stops_later_projects_and_preserves_files(self):
        self.node("a", "npm")
        self.node("b", "pnpm")
        self.exits[("npm", "ci")] = 1
        with self.assertRaises(setup.SetupError):
            self.execute()
        self.assertEqual(self.commands("pnpm"), [])
        self.assertEqual((self.root / "a/package-lock.json").read_text(), "locked")

    def test_symlinked_project_cannot_escape_worktree(self):
        self.node("client", "npm")
        shutil.rmtree(self.root / "client")
        (self.root / "client").symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(setup.SetupError, "symlinks"):
            self.execute()
        self.assertEqual(self.calls, [])

    def reusable_yarn(self):
        for source in (False, True):
            self.node(version="4.0.0", source=source)
            self.write("apps/site/package.json", "{}", source)
            self.write(".tool-versions", "nodejs 22.0.0\n", source)
        self.write("node_modules/pkg/index.js", "module.exports = 1", source=True, tracked=False)
        self.write("node_modules/.yarn-state.yml", "__metadata:\n  version: 1\n  nmMode: classic\n", source=True, tracked=False)
        self.write("apps/site/node_modules/other/index.js", "module.exports = 2", source=True, tracked=False)
        self.write(".yarn/install-state.gz", "old build state", source=True, tracked=False)
        self.write(".env.local", "EXAMPLE=synthetic", source=True, tracked=False)
        self.write(".bundle/config", "EXAMPLE: synthetic", source=True, tracked=False)
        (self.source / "node_modules/site").symlink_to(self.source / "apps/site", target_is_directory=True)
        patcher = patch.object(setup.platform, "system", return_value="Darwin")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_yarn_seeds_root_and_workspace_dependencies_and_repairs_links(self):
        self.reusable_yarn()
        self.execute()
        for name in ("node_modules/pkg/index.js", "node_modules/.yarn-state.yml",
                     "apps/site/node_modules/other/index.js"):
            self.assertEqual((self.root / name).read_bytes(), (self.source / name).read_bytes())
        self.assertEqual((self.root / "node_modules/site").resolve(), self.root / "apps/site")
        self.assertFalse((self.root / ".yarn/install-state.gz").exists())
        self.assertFalse((self.root / ".env.local").exists())
        self.assertFalse((self.root / ".bundle/config").exists())
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])
        (self.root / "node_modules/pkg/index.js").write_text("changed")
        self.assertEqual((self.source / "node_modules/pkg/index.js").read_text(), "module.exports = 1")
        self.assertEqual(list(self.root.glob(".wt-deps-*")), [])

    def test_environment_files_inside_dependencies_omit_only_their_packages(self):
        self.reusable_yarn()
        self.write("apps/site/node_modules/other/.env.local", "EXAMPLE=synthetic", source=True, tracked=False)
        self.execute()
        self.assertTrue((self.root / "node_modules/pkg/index.js").is_file())
        self.assertTrue((self.root / "apps/site/node_modules").is_dir())
        self.assertFalse((self.root / "apps/site/node_modules/other").exists())
        self.assertEqual((self.root / "node_modules/.yarn-state.yml").stat().st_mtime_ns, 0)
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])

    def test_scoped_packages_with_environment_files_are_omitted_without_losing_siblings(self):
        self.reusable_yarn()
        self.write("node_modules/@example/omitted/.env", "EXAMPLE=synthetic", source=True, tracked=False)
        self.write("node_modules/@example/retained/index.js", "module.exports = 3", source=True, tracked=False)
        self.execute()
        self.assertTrue((self.root / "node_modules/pkg/index.js").is_file())
        self.assertTrue((self.root / "node_modules/@example/retained/index.js").is_file())
        self.assertFalse((self.root / "node_modules/@example/omitted").exists())

    def test_dependency_root_environment_files_still_disable_seeding(self):
        self.reusable_yarn()
        self.write("node_modules/.env", "EXAMPLE=synthetic", source=True, tracked=False)
        self.execute()
        self.assertFalse((self.root / "node_modules").exists())
        self.assertFalse((self.root / "apps/site/node_modules").exists())
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])

    def test_older_yarn_does_not_use_partial_seeding(self):
        self.reusable_yarn()
        self.versions["yarn"] = "3.8.0"
        for source in (False, True):
            self.write("package.json", '{"packageManager":"yarn@3.8.0","workspaces":["apps/*"]}', source=source)
        self.write("node_modules/pkg/.env", "EXAMPLE=synthetic", source=True, tracked=False)
        self.execute()
        self.assertFalse((self.root / "node_modules").exists())
        self.assertFalse((self.root / "apps/site/node_modules").exists())
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])

    def test_unknown_yarn_state_version_does_not_use_partial_seeding(self):
        self.reusable_yarn()
        self.write("node_modules/.yarn-state.yml", "__metadata:\n  version: 2\n", source=True, tracked=False)
        self.write("node_modules/pkg/.env", "EXAMPLE=synthetic", source=True, tracked=False)
        self.execute()
        self.assertFalse((self.root / "node_modules").exists())
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])

    def test_untracked_link_targets_disable_seeding(self):
        self.reusable_yarn()
        self.write("local-package/index.js", "module.exports = 1", source=True, tracked=False)
        (self.source / "node_modules/local-package").symlink_to("../local-package")
        self.execute()
        self.assertFalse((self.root / "node_modules").exists())
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])

    def test_unselected_independent_projects_are_not_seeded_as_workspaces(self):
        self.reusable_yarn()
        for source in (False, True):
            self.node("e2e", "npm", source=source)
        self.write("e2e/node_modules/pkg/index.js", "module.exports = 3", source=True, tracked=False)
        self.configure([{"path": ".", "type": "node"}])
        self.execute()
        self.assertTrue((self.root / "node_modules").is_dir())
        self.assertFalse((self.root / "e2e/node_modules").exists())

    def test_source_changes_during_copy_discard_staged_dependencies(self):
        self.reusable_yarn()
        original_run = self.fake_run

        def change_source(argv, *args, **kwargs):
            result = original_run(argv, *args, **kwargs)
            if argv[0] == "/bin/cp":
                self.write("node_modules/.yarn-state.yml", "changed", source=True, tracked=False)
            return result

        with patch.object(setup, "run", side_effect=change_source):
            self.execute()
        self.assertFalse((self.root / "node_modules").exists())
        self.assertFalse((self.root / "apps/site/node_modules").exists())
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])
        self.assertEqual(list(self.root.glob(".wt-deps-*")), [])

    def test_relative_workspace_links_are_relocated(self):
        self.reusable_yarn()
        link = self.source / "node_modules/site"
        link.unlink()
        link.symlink_to("../apps/site", target_is_directory=True)
        self.execute()
        self.assertEqual((self.root / "node_modules/site").resolve(), self.root / "apps/site")

    def test_reuse_is_skipped_when_inputs_differ(self):
        for name, contents in [("yarn.lock", "different"), ("apps/site/package.json", '{"name":"new"}'),
                               (".tool-versions", "nodejs 20.0.0")]:
            with self.subTest(name=name):
                self.reusable_yarn()
                self.write(name, contents)
                self.calls.clear()
                self.execute()
                self.assertEqual(self.commands("/bin/cp"), [])
                self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])
                shutil.rmtree(self.source / "node_modules")
                shutil.rmtree(self.source / "apps/site/node_modules")

    def test_pnp_does_not_seed_node_modules(self):
        self.reusable_yarn()
        self.linker = "pnp"
        self.execute()
        self.assertEqual(self.commands("/bin/cp"), [])

    def test_no_reuse_still_installs_locked_dependencies(self):
        self.reusable_yarn()
        self.execute(reuse=False)
        self.assertEqual(self.commands("/bin/cp"), [])
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])

    def test_existing_target_dependencies_are_not_overwritten_on_retry(self):
        self.reusable_yarn()
        self.write("node_modules/pkg/index.js", "preserve", tracked=False)
        self.execute()
        self.assertEqual(self.commands("/bin/cp"), [])
        self.assertEqual((self.root / "node_modules/pkg/index.js").read_text(), "preserve")
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])

    def test_existing_shared_dependency_directories_are_rejected_before_install(self):
        self.reusable_yarn()
        for name in ["node_modules", "apps/site/node_modules"]:
            with self.subTest(path=name):
                link = self.root / name
                link.symlink_to(self.source / name, target_is_directory=True)
                try:
                    with self.assertRaisesRegex(setup.SetupError, "symlinks"):
                        self.execute(reuse=False)
                    self.assertEqual(self.commands("yarn"), [])
                finally:
                    link.unlink()

    def test_external_dependency_links_fall_back_without_installing_copies(self):
        self.reusable_yarn()
        (self.source / "node_modules/external").symlink_to(self.base / "external")
        self.execute()
        self.assertFalse((self.root / "node_modules").exists())
        self.assertFalse((self.root / "apps/site/node_modules").exists())
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])

    def test_copy_failure_falls_back_to_normal_install(self):
        self.reusable_yarn()
        original_run = self.fake_run

        def fail_copy(argv, *args, **kwargs):
            if argv[0] == "/bin/cp":
                raise setup.SetupError("copy failed")
            return original_run(argv, *args, **kwargs)

        with patch.object(setup, "run", side_effect=fail_copy):
            self.execute()
        self.assertEqual(self.calls[-1][0], ["yarn", "install", "--immutable"])
        self.assertEqual(list(self.root.glob(".wt-deps-*")), [])


class CommandTests(unittest.TestCase):
    def test_help_works_through_stow_style_symlink(self):
        with tempfile.TemporaryDirectory(prefix="wt setup link ") as temp:
            link = Path(temp) / "wt-setup"
            link.symlink_to(ROOT / "bin/.local/bin/wt-setup")
            result = subprocess.run([str(link), "--help"], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--no-reuse", result.stdout)

    @unittest.skipUnless(platform.system() == "Darwin", "requires macOS clonefile support")
    def test_real_copy_on_write_preserves_symlinks_and_independent_files(self):
        with tempfile.TemporaryDirectory(prefix="wt clone ") as temp:
            source, target = Path(temp) / "source", Path(temp) / "target"
            source.mkdir()
            (source / "index.js").write_text("original")
            (source / "alias.js").symlink_to("index.js")
            result = subprocess.run(["/bin/cp", "-cR", "-P", str(source), str(target)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "alias.js").is_symlink())
            self.assertNotEqual((source / "index.js").stat().st_ino, (target / "index.js").stat().st_ino)
            (target / "index.js").write_text("changed")
            self.assertEqual((source / "index.js").read_text(), "original")


if __name__ == "__main__":
    unittest.main()
