import argparse
import fcntl
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class SetupError(Exception):
    pass


def run(argv, cwd, env=None, capture=False, check=True):
    result = subprocess.run(argv, cwd=cwd, env=env, text=True, check=False,
                            stdout=subprocess.PIPE if capture else None)
    if check and result.returncode:
        raise SetupError(f"{shlex.join(argv)} failed in {cwd} (exit {result.returncode})")
    return result


def git(path, *args):
    return run(["git", "-C", str(path), *args], path, capture=True).stdout


def local_path(root, name):
    path = root / name
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise SetupError(f"Expected a repository-relative path: {name}")
    if not path.resolve().is_relative_to(root) or any(
            part.is_symlink() for part in [path, *path.parents] if part != root.parent):
        raise SetupError(f"Setup paths must not traverse symlinks: {name}")
    return path


def tracked_files(root):
    return set(filter(None, git(root, "ls-files", "-z").split("\0")))


LOCKS = {"yarn": ("yarn.lock",), "npm": ("npm-shrinkwrap.json", "package-lock.json"),
         "pnpm": ("pnpm-lock.yaml",)}


@dataclass
class Project:
    path: Path
    kind: str
    workspaces: tuple = ()
    command: tuple = ()


def discover_projects(files):
    projects = []
    for name in sorted(files):
        path = Path(name)
        if path.name == "Gemfile.lock" and str(path.parent / "Gemfile") in files:
            projects.append(Project(path.parent, "ruby"))
        elif (path.name in {lock for locks in LOCKS.values() for lock in locks}
              and str(path.parent / "package.json") in files):
            project = Project(path.parent, "node")
            if project not in projects:
                projects.append(project)
    return projects


def load_projects(root, common, files):
    config_path = common / "worktree-setup.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if not isinstance(config, dict) or set(config) - {"projects"}:
        raise SetupError("worktree-setup.json must be an object with an optional projects array")
    if "projects" not in config:
        return discover_projects(files)
    if not isinstance(config["projects"], list):
        raise SetupError("projects must be an array")
    projects = []
    for item in config["projects"]:
        if not isinstance(item, dict) or set(item) - {"path", "type", "workspaces", "command"}:
            raise SetupError("Invalid setup project")
        name, kind = item.get("path"), item.get("type")
        if not isinstance(name, str) or kind not in {"node", "ruby", "command"}:
            raise SetupError("Each setup project needs a path and type (node, ruby, or command)")
        local_path(root, name)
        workspaces, command = item.get("workspaces", []), item.get("command", [])
        for value in (workspaces, command):
            if not isinstance(value, list) or any(not isinstance(s, str) or not s for s in value):
                raise SetupError("workspaces and command must be arrays of nonempty strings")
        if (workspaces and kind != "node") or (command and kind != "command"):
            raise SetupError("workspaces require a node project; command requires a command project")
        if kind == "command" and not command:
            raise SetupError("A command project needs a command")
        project = Project(Path(name), kind, tuple(workspaces), tuple(command))
        if any(p.path == project.path and p.kind == kind for p in projects):
            raise SetupError(f"Duplicate setup project: {name} ({kind})")
        projects.append(project)
    return projects


def ancestor_file(root, path, name):
    for directory in [path, *path.parents]:
        candidate = directory / name
        if candidate.is_file():
            local_path(root, str(candidate.relative_to(root)))
            return candidate
        if directory == root:
            break
    return None


def tool_version(root, path, tool):
    for directory in [path, *path.parents]:
        versions = directory / ".tool-versions"
        if versions.is_file():
            local_path(root, str(versions.relative_to(root)))
            match = re.search(rf"^{tool}\s+([^\n#]+)", versions.read_text(), re.MULTILINE)
            if match:
                return match[1].strip()
        if directory == root:
            break
    return None


def tool_env(root, path):
    env = dict(os.environ)
    for tool, filenames in {"ruby": (".ruby-version",), "nodejs": (".node-version", ".nvmrc"),
                            "yarn": (), "pnpm": (), "python": ()}.items():
        declared = tool_version(root, path, tool)
        if declared:
            env[f"ASDF_{tool.upper()}_VERSION"] = declared
            continue
        for filename in filenames:
            version_file = ancestor_file(root, path, filename)
            if version_file:
                version = version_file.read_text().strip().removeprefix("ruby-").removeprefix("v")
                if not re.fullmatch(r"\d+\.\d+\.\d+", version):
                    raise SetupError(f"An exact runtime version is required in {version_file}")
                env[f"ASDF_{tool.upper()}_VERSION"] = version
                break
    return env


def setup_runtimes(root, path, installed, env):
    directories = [path, *path.parents]
    for directory in reversed(directories[:directories.index(root) + 1]):
        versions = directory / ".tool-versions"
        if versions.is_file() and versions not in installed:
            local_path(root, str(versions.relative_to(root)))
            run(["asdf", "install"], directory, tool_env(root, directory))
            installed.add(versions)
    for tool, filenames in {"ruby": (".ruby-version",), "nodejs": (".node-version", ".nvmrc")}.items():
        key = f"ASDF_{tool.upper()}_VERSION"
        legacy = any(ancestor_file(root, path, name) for name in filenames)
        if legacy and not tool_version(root, path, tool):
            identity = (tool, env[key])
            if identity not in installed:
                run(["asdf", "install", tool, env[key]], path, env)
                installed.add(identity)


def node_manager(root, project, files):
    path = local_path(root, str(project.path))
    manifest_path = local_path(root, str(project.path / "package.json"))
    if not manifest_path.is_file():
        raise SetupError(f"Missing package.json in {path}")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or not isinstance(manifest.get("packageManager", ""), str):
        raise SetupError(f"Invalid package.json in {path}")
    declared = manifest.get("packageManager", "")
    match = re.fullmatch(r"(yarn|npm|pnpm)@(\d+\.\d+\.\d+(?:-[\w.-]+)?)(?:\+.+)?", declared)
    if declared and not match:
        raise SetupError(f"Unsupported or unpinned packageManager in {manifest_path}")
    available = {manager: next((lock for lock in locks
                                if str(project.path / lock) in files), None)
                 for manager, locks in LOCKS.items()}
    available = {manager: lock for manager, lock in available.items() if lock}
    if match:
        manager, version = match.groups()
        if manager not in available:
            raise SetupError(f"Missing {manager} lockfile in {path}")
    elif len(available) == 1:
        manager, version = next(iter(available)), None
    else:
        raise SetupError(f"Cannot choose a package manager in {path}; set packageManager")
    local_path(root, str(project.path / available[manager]))
    return manager, version, available[manager]


def project_files(files, relative, node_roots):
    prefix = relative.parts
    nested = [p for p in node_roots if p != relative and p.is_relative_to(relative)]
    return {name for name in files if Path(name).parts[:len(prefix)] == prefix
            and not any(Path(name).is_relative_to(p) for p in nested)
            and (Path(name).name in {"package.json", "yarn.lock", ".yarnrc.yml", ".yarnrc",
                                     ".npmrc", ".tool-versions", ".node-version", ".nvmrc"}
                 or ".yarn" in Path(name).parts)}


def same_inputs(root, source, names):
    for name in names:
        left, right = local_path(root, name), local_path(source, name)
        if not left.is_file() or not right.is_file() or left.read_bytes() != right.read_bytes():
            return False
    return True


def inspect_dependencies(original, source, root, directories):
    candidates, links, excluded = [], [], set()
    pending = [original]
    while pending:
        directory = pending.pop()
        if any(directory.relative_to(original).is_relative_to(p) for p in excluded):
            continue
        with os.scandir(directory) as entries:
            for entry in entries:
                name = entry.name
                if name in {".env", ".npmrc", ".netrc", ".pypirc", ".bundle"} or name.startswith(".env."):
                    relative = Path(entry.path).relative_to(original)
                    depth = 2 if relative.parts[0].startswith("@") else 1
                    if len(relative.parts) <= depth or relative.parts[0].startswith("."):
                        raise SetupError("Dependency root contains local environment or authentication configuration")
                    excluded.add(Path(*relative.parts[:depth]))
                    break
                if entry.is_symlink():
                    candidates.append(Path(entry.path))
                elif entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
    for link in candidates:
        if any(link.relative_to(original).is_relative_to(p) for p in excluded):
            continue
        target = (link.parent / os.readlink(link)).resolve()
        if not target.is_relative_to(source):
            raise SetupError("Dependency links outside the source checkout cannot be reused")
        relative_target = target.relative_to(source)
        destination_target = local_path(root, str(relative_target))
        if not destination_target.exists() and not any(relative_target.is_relative_to(p) for p in directories):
            raise SetupError("Dependency link target is unavailable in the new worktree")
        destination_link = root / link.relative_to(source)
        links.append((link.relative_to(original), os.path.relpath(destination_target, destination_link.parent)))
    return links, excluded


def clone_dependencies(original, staged, excluded, cwd):
    if not excluded:
        run(["/bin/cp", "-cR", "-P", str(original), str(staged)], cwd, capture=True)
        return
    staged.mkdir()
    sources = []
    for entry in original.iterdir():
        relative = Path(entry.name)
        if relative in excluded:
            continue
        nested = {p.relative_to(relative) for p in excluded if p.is_relative_to(relative)}
        if nested:
            clone_dependencies(entry, staged / entry.name, nested, cwd)
        else:
            sources.append(str(entry))
    for start in range(0, len(sources), 128):
        run(["/bin/cp", "-cR", "-P", *sources[start:start + 128], str(staged)], cwd, capture=True)


def file_identity(path):
    stat = path.stat()
    return stat.st_ino, stat.st_size, stat.st_mtime_ns


def dependency_directories(project, files, node_roots):
    names = project_files(files, project.path, node_roots)
    return {project.path / "node_modules", *(Path(name).parent / "node_modules"
            for name in names if Path(name).name == "package.json")}


def seed_yarn(root, source, project, files, source_files, node_roots, command, env, allow_partial):
    if platform.system() != "Darwin" or source == root or not source.is_dir():
        return
    path = root / project.path
    if run([*command, "config", "get", "nodeLinker"], path, env, capture=True).stdout.strip() != "node-modules":
        return
    names = project_files(files, project.path, node_roots)
    if names != project_files(source_files, project.path, node_roots) or not same_inputs(root, source, names):
        return
    identity = ["node", "-p", "JSON.stringify([process.version,process.platform,process.arch,process.versions.modules])"]
    current = run(identity, path, env, capture=True).stdout
    previous = run(identity, source / project.path, tool_env(source, source / project.path), capture=True,
                   check=False)
    if previous.returncode or current != previous.stdout:
        return
    marker = source / project.path / "node_modules/.yarn-state.yml"
    if not marker.is_file() or marker.is_symlink():
        return
    marker_identity = file_identity(marker)
    directories = dependency_directories(project, files, node_roots)
    if any(os.path.lexists(root / name) for name in directories):
        return
    copies, excluded_count = [], 0
    with tempfile.TemporaryDirectory(prefix=".wt-deps-", dir=path) as temp:
        for name in sorted(directories):
            original = local_path(source, str(name))
            if not original.is_dir():
                continue
            if original.stat().st_dev != path.stat().st_dev:
                return
            links, excluded = inspect_dependencies(original, source, root, directories)
            if excluded and (not allow_partial or not re.search(r"^  version: 1$", marker.read_text(), re.MULTILINE)):
                return
            excluded_count += len(excluded)
            staged = Path(temp) / str(len(copies))
            clone_dependencies(original, staged, excluded, path)
            for relative, target in links:
                link = staged / relative
                link.unlink()
                link.symlink_to(target)
            copies.append((staged, local_path(root, str(name))))
        if file_identity(marker) != marker_identity or not same_inputs(root, source, names):
            return
        if excluded_count:
            for staged, destination in copies:
                if destination == path / "node_modules":
                    # Yarn rescans missing packages when directories are newer than its state file.
                    os.utime(staged / ".yarn-state.yml", (0, 0))
        for staged, destination in copies:
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged.rename(destination)
    if copies:
        print(f"wt-setup: seeded {len(copies)} dependency directories in {path}", flush=True)


def setup_node(root, source, project, files, source_files, node_roots, env, reuse):
    path = root / project.path
    manager, pinned, _ = node_manager(root, project, files)
    for directory in dependency_directories(project, files, node_roots):
        local_path(root, str(directory))
    corepack = (manager != "npm" and shutil.which("corepack")
                and run(["corepack", "--version"], path, env, capture=True, check=False).returncode == 0)
    command = ["corepack", manager] if corepack else [manager]
    version = run([*command, "--version"], path, env, capture=True).stdout.strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[\w.-]+)?", version):
        raise SetupError(f"Cannot determine {manager} version in {path}")
    if pinned and version != pinned:
        raise SetupError(f"{manager} {pinned} required in {path}, found {version}")
    modern_yarn = manager == "yarn" and int(version.split(".")[0]) >= 2
    if project.workspaces and not modern_yarn:
        raise SetupError("Workspace selection currently requires Yarn 2 or later")
    if modern_yarn and reuse:
        try:
            seed_yarn(root, source, project, files, source_files, node_roots, command, env,
                      allow_partial=int(version.split(".")[0]) >= 4)
        except (OSError, RuntimeError, SetupError) as error:
            print(f"wt-setup: reuse unavailable ({error}); continuing with install", file=sys.stderr)
    env = {**env, "YARN_ENABLE_IMMUTABLE_INSTALLS": "true"} if modern_yarn else env
    if project.workspaces:
        if any(name.startswith("-") for name in project.workspaces):
            raise SetupError("Workspace names must not start with a dash")
        args = ["workspaces", "focus", *project.workspaces]
    elif manager == "npm":
        args = ["ci"]
    else:
        args = ["install", "--immutable" if modern_yarn else "--frozen-lockfile"]
    run([*command, *args], path, env)


def setup_ruby(root, project, env):
    path = root / project.path
    lock = local_path(root, str(project.path / "Gemfile.lock"))
    local_path(root, str(project.path / "Gemfile"))
    if not lock.is_file() or not (path / "Gemfile").is_file():
        raise SetupError(f"A Gemfile and Gemfile.lock are required in {path}")
    match = re.search(r"^BUNDLED WITH\n\s+(\d+\.\d+\.\d+)\s*$", lock.read_text(), re.MULTILINE)
    if not match:
        raise SetupError(f"Missing exact BUNDLED WITH version in {lock}")
    version = match[1]
    command = ["bundle", f"_{version}_"]
    env = {**env, "BUNDLE_GEMFILE": str(path / "Gemfile")}
    try:
        available = run([*command, "--version"], path, env, capture=True, check=False).returncode == 0
    except FileNotFoundError:
        available = False
    if not available:
        run(["gem", "install", "bundler", "--version", version, "--no-document"], path, env)
    frozen = {**env, "BUNDLE_FROZEN": "true", "BUNDLE_CLEAN": "false"}
    for setting, value in (("frozen", "true"), ("clean", "false")):
        effective = run([*command, "config", "get", setting, "--parseable"], path, frozen,
                        capture=True).stdout.strip()
        if effective != f"{setting}={value}" and not (value == "false" and not effective):
            raise SetupError(f"Bundler configuration overrides safe {setting}={value} in {path}")
    if run([*command, "check"], path, frozen, check=False).returncode:
        run([*command, "install"], path, frozen)
    run([*command, "exec", "ruby", "-e", "exit"], path, frozen)


def setup(root, source=None, reuse=True):
    root = Path(root).resolve()
    root = Path(git(root, "rev-parse", "--show-toplevel").strip()).resolve()
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    with (common / "worktree-setup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        setup_locked(root, common, source, reuse)


def setup_locked(root, common, source, reuse):
    if source is None:
        source = common.parent
    source = Path(source).resolve()
    files = tracked_files(root)
    projects = load_projects(root, common, files)
    source_files = set()
    if reuse and source != root and source.is_dir():
        try:
            if Path(git(source, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()) == common:
                source_files = tracked_files(source)
        except (OSError, SetupError):
            pass
    if not source_files:
        reuse = False
    installed = set()
    setup_runtimes(root, root, installed, tool_env(root, root))
    node_roots = [p.path for p in discover_projects(files) if p.kind == "node"]
    for project in projects:
        path = local_path(root, str(project.path))
        if not path.is_dir():
            raise SetupError(f"Missing setup directory: {path}")
        env = tool_env(root, path)
        setup_runtimes(root, path, installed, env)
        print(f"wt-setup: {project.kind} setup in {path}", flush=True)
        if project.kind == "node":
            setup_node(root, source, project, files, source_files, node_roots, env, reuse)
        elif project.kind == "ruby":
            setup_ruby(root, project, env)
        else:
            run(list(project.command), path, env)


def main():
    parser = argparse.ArgumentParser(description="Set up worktree runtimes and locked dependencies")
    parser.add_argument("--path", type=Path, default=Path.cwd(), help="worktree path (default: current repository)")
    parser.add_argument("--source", type=Path, help="dependency source (default: primary checkout)")
    parser.add_argument("--no-reuse", action="store_true", help="do not seed dependency directories")
    args = parser.parse_args()
    try:
        setup(args.path, args.source, not args.no_reuse)
    except (SetupError, OSError, RuntimeError, ValueError) as error:
        print(f"wt-setup: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("wt-setup: interrupted; worktree preserved", file=sys.stderr)
        sys.exit(130)
