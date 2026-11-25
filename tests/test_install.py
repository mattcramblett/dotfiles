import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "install.sh").read_text()
IGNORE_SETUP = INSTALLER[INSTALLER.index("global_git_ignore="):INSTALLER.index("\nclone_dependency https:")]


class GlobalIgnoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dotfiles ignore ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = {**os.environ, "HOME": str(self.home),
                    "GIT_CONFIG_GLOBAL": str(self.home / ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
        self.env.pop("XDG_CONFIG_HOME", None)

    def install_ignore(self):
        result = subprocess.run(["bash", "-eu", "-o", "pipefail", "-c", IGNORE_SETUP],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_ignore_covers_root_and_nested_tasks_only(self):
        self.install_ignore()
        self.assertEqual((self.home / ".config/git/ignore").read_text(), "\n**/.pi/tasks/\n")
        for path, ignored in [(".pi/tasks/output.json", True),
                              ("workspace/.pi/tasks/output.json", True),
                              ("workspace/nested/.pi/tasks/output.json", True),
                              ("workspace/.pi/settings.json", False)]:
            with self.subTest(path=path):
                result = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--no-index", "-q", path],
                                        env=self.env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0 if ignored else 1, result.stderr)

    def test_existing_entries_are_preserved_without_duplicates(self):
        ignore = self.home / ".config/git/ignore"
        ignore.parent.mkdir(parents=True)
        original = "local-only.txt\n.pi/tasks/\n"
        ignore.write_text(original)
        self.install_ignore()
        self.install_ignore()
        self.assertEqual(ignore.read_text(), original + "\n**/.pi/tasks/\n")

    def test_xdg_config_home_is_respected(self):
        self.env["XDG_CONFIG_HOME"] = str(self.home / "custom config")
        self.install_ignore()
        self.assertEqual((self.home / "custom config/git/ignore").read_text(), "\n**/.pi/tasks/\n")
        self.assertFalse((self.home / ".config/git/ignore").exists())

    def test_explicit_global_ignore_path_is_respected(self):
        ignore = self.home / "custom ignore"
        (self.home / ".gitconfig").write_text(f'[core]\n\texcludesFile = "{ignore}"\n')
        self.install_ignore()
        self.assertEqual(ignore.read_text(), "\n**/.pi/tasks/\n")
        self.assertFalse((self.home / ".config/git/ignore").exists())


if __name__ == "__main__":
    unittest.main()
