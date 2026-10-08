"""install.sh in throwaway HOME folders, with offline safety regressions.

The end-to-end class clones upstream once from GitHub (or takes $GJS_UPSTREAM, a
local clone). Without network only that class skips, unless GJS_REQUIRE_NETWORK=1
(set in CI). Safety tests always run against an invented local git repository.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install.sh"
UPSTREAM_URL = "https://github.com/kerpopule/hermes-jev-skills"
STRIP = ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "VENICE_API_KEY", "OPENCODE_ZEN_API_KEY",
         "TYPESAFE_BASE_URL", "JEV_PROXY_API_KEY", "JEV_PROVIDER", "GROKBOT_SKILLS_DIR",
         "JEV_UPSTREAM_DIR", "JEV_UPSTREAM_REF", "JEV_UPSTREAM_URL", "JEV_BIN_DIR", "XDG_STATE_HOME")
SENTINEL = "tsk-sentinel-value-that-must-never-be-written-0000"


class InstallCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="home-", dir=self.work))
        self.skills = self.home / "grokbot-workflows"
        self.env = {k: v for k, v in os.environ.items() if k not in STRIP}
        self.env.update(HOME=str(self.home), TYPESAFE_API_KEY=SENTINEL,
                        GROKBOT_DEFAULT_SKILLS_PROBE=str(self.home / "no-such-grokbot-dir"))

    def run_install(self, *args, check=True, cwd=None, installer=INSTALL):
        proc = subprocess.run(["bash", str(installer), "--upstream", self.upstream, *args],
                              capture_output=True, text=True, env=self.env, timeout=300, cwd=cwd)
        if check:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn(SENTINEL, proc.stdout + proc.stderr)
        return proc

    def verify(self, *args):
        env = {k: v for k, v in self.env.items() if k != "TYPESAFE_API_KEY"}
        proc = subprocess.run([sys.executable, str(REPO / "tools" / "verify_skills.py"), "--home", str(self.home), *args],
                              capture_output=True, text=True, env=env, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def files_under_home(self):
        return sorted(p for p in self.home.rglob("*") if ".git" not in p.parts)

    def assert_sentinel_never_written(self):
        for path in self.home.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                self.assertNotIn(SENTINEL, path.read_text(errors="replace"), path)


class Install(InstallCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="gjs-install-"))
        cls.addClassCleanup(shutil.rmtree, cls.work, ignore_errors=True)
        local = os.environ.get("GJS_UPSTREAM")
        if local:
            cls.upstream = local
            return
        cls.upstream = str(cls.work / "upstream-cache")
        proc = subprocess.run(["git", "clone", "--quiet", UPSTREAM_URL, cls.upstream],
                              capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            if os.environ.get("GJS_REQUIRE_NETWORK") == "1":
                raise RuntimeError(f"could not clone upstream: {proc.stderr}")
            raise unittest.SkipTest("no network to clone upstream; set GJS_UPSTREAM to a local clone")

    def test_check_changes_nothing(self):
        proc = self.run_install("--check", "--skills-dir", str(self.skills))
        self.assertIn("would clone", proc.stdout)
        self.assertIn("would copy 10 skills", proc.stdout)
        self.assertEqual(self.files_under_home(), [])

    def test_full_cycle(self):
        proc = self.run_install("--skills-dir", str(self.skills))
        self.assertIn("jev       0.22.1", proc.stdout)
        launcher = self.home / ".local" / "bin" / "jev"
        self.assertTrue(os.access(launcher, os.X_OK))
        head = subprocess.run(["git", "-C", str(self.home / ".local/share/hermes-jev-skills"), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(head, "a6f6344bae3411b2afaabd640dc28cda736e8894")
        helped = subprocess.run([str(launcher), "--help"], capture_output=True, text=True, env=self.env)
        self.assertEqual(helped.returncode, 0)
        self.assertIn("search", helped.stdout)
        self.assertEqual(sorted(p.name for p in self.skills.iterdir()), sorted(p.name for p in (REPO / "skills").iterdir()))

        self.verify()            # no key: documented fail-open shapes
        self.verify("--mock")    # mock: documented success shapes
        self.assertFalse((self.home / ".hermes").exists(), "launcher must keep jev state out of ~/.hermes")

        again = self.run_install("--skills-dir", str(self.skills))
        self.assertEqual(again.stdout.count("(unchanged)"), 10)

        edited = self.skills / "jev-watch-run" / "SKILL.md"
        edited.write_text(edited.read_text() + "\nlocal note\n")
        third = self.run_install("--skills-dir", str(self.skills))
        self.assertIn("jev-watch-run SKIPPED", third.stdout)
        self.assertTrue(edited.read_text().endswith("local note\n"))

        self.assert_sentinel_never_written()
        # Ignore caches made by verification when exercising clean-clone removal.
        for cache in (self.home / ".local/share/hermes-jev-skills").rglob("__pycache__"):
            shutil.rmtree(cache)
        gone = self.run_install("--uninstall", "--skills-dir", str(self.skills))
        self.assertIn("kept      " + str(edited.resolve()), gone.stdout)
        self.assertFalse(launcher.exists())
        self.assertFalse((self.home / ".local/share/hermes-jev-skills").exists())
        self.assertEqual([p.name for p in self.skills.iterdir()], ["jev-watch-run"])

    def test_refuses_foreign_launcher(self):
        launcher = self.home / ".local" / "bin" / "jev"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\necho someone else's jev\n")
        proc = self.run_install("--no-skills", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not written by this installer", proc.stderr)
        self.assertEqual(launcher.read_text(), "#!/bin/sh\necho someone else's jev\n")
        self.run_install("--uninstall")
        self.assertTrue(launcher.exists())

    def test_default_skills_dir_only_if_it_exists(self):
        proc = self.run_install("--check")
        self.assertIn("skills    none", proc.stdout)
        probe = self.home / "grokbot-default"
        probe.mkdir()
        self.env["GROKBOT_DEFAULT_SKILLS_PROBE"] = str(probe)
        self.run_install()
        self.assertTrue((probe / "jev-search-loop" / "SKILL.md").is_file())
        self.run_install("--uninstall")
        self.assertEqual(list(probe.iterdir()), [])

    def test_no_skills(self):
        probe = self.home / "grokbot-default"
        probe.mkdir()
        self.env["GROKBOT_DEFAULT_SKILLS_PROBE"] = str(probe)
        proc = self.run_install("--no-skills")
        self.assertIn("skills    not installed", proc.stdout)
        self.assertEqual(list(probe.iterdir()), [])


class InstallSafety(InstallCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="gjs-install-offline-"))
        cls.addClassCleanup(shutil.rmtree, cls.work, ignore_errors=True)
        upstream = cls.work / "upstream"
        (upstream / "bin").mkdir(parents=True)
        cli = upstream / "bin/jev"
        cli.write_text('#!/bin/sh\nprintf "fixture-version\\n"\n')
        cli.chmod(0o755)
        subprocess.run(["git", "init", "--quiet", str(upstream)], check=True)
        subprocess.run(["git", "-C", str(upstream), "add", "bin/jev"], check=True)
        subprocess.run(["git", "-C", str(upstream), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
                        "-c", "core.hooksPath=/dev/null", "commit", "--quiet", "-m", "fixture"], check=True)
        cls.upstream = str(upstream)
        cls.ref = subprocess.check_output(["git", "-C", cls.upstream, "rev-parse", "HEAD"], text=True).strip()

    def setUp(self):
        super().setUp()
        self.env["JEV_UPSTREAM_REF"] = self.ref
        self.checkout = self.home / ".local/share/hermes-jev-skills"
        self.launcher = self.home / ".local/bin/jev"

    def existing_checkout(self):
        self.checkout.parent.mkdir(parents=True)
        subprocess.run(["git", "clone", "--quiet", self.upstream, str(self.checkout)], check=True)

    def git(self, *args, directory=None):
        return subprocess.check_output(["git", "-C", str(directory or self.checkout), *args], text=True).strip()

    def commit_fixture(self, directory, name, content):
        (directory / name).write_text(content)
        self.git("add", name, directory=directory)
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                 "commit", "--quiet", "-m", "invented local work", directory=directory)
        return self.git("rev-parse", "HEAD", directory=directory)

    def assert_committed_work_preserved(self, commit):
        self.assertEqual(self.git("status", "--porcelain"), "")
        head = self.git("rev-parse", "HEAD")
        refs = self.git("show-ref")
        plan = self.run_install("--check", "--no-skills")
        self.assertIn("local commits", plan.stdout)
        update = self.run_install("--no-skills", check=False)
        self.assertNotEqual(update.returncode, 0)
        self.assertIn("local commits", update.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("show-ref"), refs)
        gone = self.run_install("--uninstall")
        self.assertIn("local changes, files or commits", gone.stdout)
        self.assertTrue(self.checkout.is_dir())
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("show-ref"), refs)
        self.assertEqual(self.git("cat-file", "-t", commit), "commit")

    def test_does_not_take_ownership_of_existing_checkout(self):
        self.existing_checkout()
        self.run_install("--no-skills")
        self.assertFalse((self.checkout / ".git/grokbot-jev-skills-managed").exists())
        note = self.checkout / "user-note.txt"
        note.write_text("user's unrelated work\n")
        self.run_install("--uninstall")
        self.assertTrue(self.checkout.exists())
        self.assertEqual(note.read_text(), "user's unrelated work\n")

    def test_dirty_checkout_update_stops_before_changes(self):
        self.existing_checkout()
        note = self.checkout / "user-note.txt"
        note.write_text("uncommitted work\n")
        before = subprocess.check_output(["git", "-C", str(self.checkout), "rev-parse", "HEAD"], text=True)
        plan = self.run_install("--check", "--no-skills")
        self.assertIn("CONFLICT", plan.stdout)
        self.assertIn("local changes or files", plan.stdout)
        proc = self.run_install("--no-skills", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("local changes or files", proc.stderr)
        self.assertEqual(subprocess.check_output(["git", "-C", str(self.checkout), "rev-parse", "HEAD"], text=True), before)
        self.assertFalse(self.launcher.exists())
        self.assertEqual(note.read_text(), "uncommitted work\n")

    def test_legacy_empty_marker_does_not_prove_checkout_ownership(self):
        self.existing_checkout()
        (self.checkout / ".git/grokbot-jev-skills-managed").touch()
        self.run_install("--no-skills")
        self.run_install("--uninstall")
        self.assertTrue(self.checkout.exists(), "old releases marked adopted user checkouts too")

    def test_uninstall_preserves_managed_checkout_with_local_edit(self):
        self.run_install("--no-skills")
        cli = self.checkout / "bin/jev"
        cli.write_text(cli.read_text() + "# a user's local change\n")
        proc = self.run_install("--uninstall")
        self.assertIn("local changes, files or commits", proc.stdout)
        self.assertTrue(cli.read_text().endswith("# a user's local change\n"))

    def test_uninstall_preserves_ignored_local_file(self):
        self.run_install("--no-skills")
        with (self.checkout / ".git/info/exclude").open("a") as exclude:
            exclude.write("\nprivate-note\n")
        note = self.checkout / "private-note"
        note.write_text("invented private fixture\n")
        proc = self.run_install("--uninstall")
        self.assertIn("local changes, files or commits", proc.stdout)
        self.assertEqual(note.read_text(), "invented private fixture\n")

    def test_clean_local_commit_survives_update_and_uninstall(self):
        self.run_install("--no-skills")
        commit = self.commit_fixture(self.checkout, "local-work.txt", "invented committed work\n")
        self.assert_committed_work_preserved(commit)
        self.assertEqual((self.checkout / "local-work.txt").read_text(), "invented committed work\n")

    def test_local_ref_commit_survives_update_and_uninstall(self):
        self.run_install("--no-skills")
        commit = self.commit_fixture(self.checkout, "local-work.txt", "invented branch work\n")
        self.git("branch", "user-work", commit)
        self.git("reset", "--hard", self.ref)
        self.git("reflog", "expire", "--expire=now", "--all")
        self.assert_committed_work_preserved(commit)
        self.assertEqual(self.git("rev-parse", "user-work"), commit)

    def test_reflog_only_commit_survives_update_and_uninstall(self):
        self.run_install("--no-skills")
        commit = self.commit_fixture(self.checkout, "local-work.txt", "invented detached work\n")
        self.git("reset", "--hard", self.ref)
        self.assertNotIn(commit, self.git("rev-list", "--all").splitlines())
        self.assertIn(commit, self.git("rev-list", "--all", "--reflog").splitlines())
        self.assert_committed_work_preserved(commit)
        self.assertIn(commit, self.git("rev-list", "--all", "--reflog").splitlines())

    def test_new_ref_cannot_overwrite_ignored_local_file(self):
        upstream = self.home / "upstream-update-fixture"
        subprocess.run(["git", "clone", "--quiet", self.upstream, str(upstream)], check=True)
        self.upstream = str(upstream)
        self.run_install("--no-skills")
        with (self.checkout / ".git/info/exclude").open("a") as exclude:
            exclude.write("\nprivate-note\n")
        note = self.checkout / "private-note"
        note.write_text("invented ignored local work\n")
        next_ref = self.commit_fixture(upstream, "private-note", "new upstream tracked text\n")
        self.assertEqual(self.git("status", "--porcelain"), "")
        launcher_before = self.launcher.read_bytes()
        proc = self.run_install("--ref", next_ref, "--no-skills", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(note.read_text(), "invented ignored local work\n")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.ref)
        self.assertEqual(self.launcher.read_bytes(), launcher_before)

    def test_managed_marker_does_not_bypass_origin_check(self):
        self.run_install("--no-skills")
        subprocess.run(["git", "-C", str(self.checkout), "remote", "set-url", "origin", "unrelated-origin"], check=True)
        proc = self.run_install("--no-skills", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unrelated-origin", proc.stderr)

    def test_relative_upstream_dir_launcher_works_from_other_cwd(self):
        self.run_install("--dir", "relative-upstream", "--no-skills", cwd=self.home)
        proc = subprocess.run([str(self.launcher), "--version"], capture_output=True,
                              text=True, env=self.env, cwd=self.work, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "fixture-version\n")

    def test_unsafe_physical_upstream_path_is_rejected_before_launcher_execution(self):
        physical_parent = self.home / "unsafe-$(touch marker)"
        physical_parent.mkdir()
        safe_parent = self.home / "safe-parent"
        safe_parent.symlink_to(physical_parent, target_is_directory=True)
        proc = self.run_install("--dir", str(safe_parent / "checkout"), "--no-skills",
                                check=False, cwd=self.home)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("backticks or backslashes", proc.stderr)
        self.assertFalse((self.home / "marker").exists())
        self.assertFalse(self.launcher.exists())

    def test_physical_upstream_trailing_newline_is_not_stripped(self):
        physical_checkout = self.home / "physical-checkout\n"
        subprocess.run(["git", "clone", "--quiet", self.upstream, str(physical_checkout)], check=True)
        safe_checkout = self.home / "safe-checkout"
        safe_checkout.symlink_to(physical_checkout, target_is_directory=True)
        proc = self.run_install("--dir", str(safe_checkout), "--no-skills", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("tabs or newlines", proc.stderr)
        self.assertFalse(self.launcher.exists())
        self.assertFalse((self.home / "physical-checkout").exists())

    def test_local_relative_upstream_is_idempotent(self):
        relative = os.path.relpath(self.upstream, self.home)
        self.run_install("--upstream", relative, "--no-skills", cwd=self.home)
        self.run_install("--upstream", relative, "--no-skills", cwd=self.home)
        self.run_install("--upstream", relative, "--uninstall", cwd=self.home)
        self.assertFalse(self.checkout.exists())

    def test_bin_dir_cannot_overwrite_the_upstream_cli(self):
        proc = self.run_install("--bin-dir", str(self.checkout / "bin"), "--no-skills", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not written by this installer", proc.stderr)
        self.assertEqual((self.checkout / "bin/jev").read_text(), '#!/bin/sh\nprintf "fixture-version\\n"\n')

    def test_force_does_not_follow_skill_links(self):
        external = self.home / "unrelated-workflow"
        external.mkdir()
        original = "unrelated user's skill\n"
        external_skill = external / "SKILL.md"
        external_skill.write_text(original)
        self.skills.mkdir()
        (self.skills / "jev-search-loop").symlink_to(external, target_is_directory=True)
        file_link = self.skills / "jev-watch-run/SKILL.md"
        file_link.parent.mkdir()
        file_link.symlink_to(external_skill)
        proc = self.run_install("--skills-dir", str(self.skills), "--force")
        self.assertIn("jev-search-loop SKIPPED", proc.stdout)
        self.assertIn("jev-watch-run SKIPPED", proc.stdout)
        self.assertEqual(external_skill.read_text(), original)
        self.assertTrue(file_link.is_symlink())

    def test_uninstall_does_not_follow_retargeted_skill_directory(self):
        self.run_install("--skills-dir", str(self.skills))
        slug_dir = self.skills / "jev-search-loop"
        external = self.home / "unrelated-workflow"
        external.mkdir()
        external_skill = external / "SKILL.md"
        shutil.copy(slug_dir / "SKILL.md", external_skill)
        (slug_dir / "SKILL.md").unlink()
        slug_dir.rmdir()
        slug_dir.symlink_to(external, target_is_directory=True)
        proc = self.run_install("--uninstall")
        self.assertIn("symbolic link or changed directory", proc.stdout)
        self.assertTrue(external_skill.exists())
        self.assertTrue(slug_dir.is_symlink())

    def test_manifest_updates_space_and_backslash_paths(self):
        skills = self.home / "workflow \\ collection"
        fixture_source = self.home / "installer-source"
        fixture_skill = fixture_source / "skills/fixture/SKILL.md"
        fixture_skill.parent.mkdir(parents=True)
        fixture_skill.write_text("initial fixture skill\n")
        installer = fixture_source / "install.sh"
        shutil.copy(INSTALL, installer)
        (fixture_source / "tools").mkdir()
        shutil.copy(REPO / "tools/jev_runtime.py", fixture_source / "tools/jev_runtime.py")
        self.run_install("--skills-dir", str(skills), installer=installer)
        fixture_skill.write_text("updated fixture skill\n")
        self.run_install("--skills-dir", str(skills), installer=installer)
        self.assertEqual((skills / "fixture/SKILL.md").read_text(), "updated fixture skill\n")
        self.run_install("--uninstall", installer=installer)
        self.assertEqual(list(skills.iterdir()), [])

    def test_manifest_rejects_ambiguous_paths_without_writes(self):
        for suffix in ("tab\tpath", "newline\npath"):
            with self.subTest(suffix=suffix):
                proc = self.run_install("--check", "--skills-dir", str(self.home / suffix), check=False)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("tabs or newlines", proc.stderr)
                self.assertEqual(self.files_under_home(), [])

    def test_physical_skills_paths_reject_tabs_and_newlines(self):
        for index, suffix in enumerate(("tab\tpath", "embedded\npath", "trailing-newline\n")):
            with self.subTest(suffix=suffix):
                physical = self.home / suffix
                physical.mkdir()
                logical = self.home / f"safe-skills-{index}"
                logical.symlink_to(physical, target_is_directory=True)
                proc = self.run_install("--skills-dir", str(logical), check=False)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("tabs or newlines", proc.stderr)
                self.assertEqual(list(physical.iterdir()), [])
                self.assertFalse((self.home / ".local/state/grokbot-jev-skills/installed-skills.tsv").exists())
                if suffix.endswith("\n"):
                    self.assertFalse((self.home / suffix.rstrip("\n")).exists())

    def test_physical_manifest_state_paths_reject_tabs_and_newlines(self):
        for index, suffix in enumerate(("state\tpath", "state\npath", "state-trailing\n")):
            with self.subTest(suffix=suffix):
                physical = self.home / suffix
                physical.mkdir()
                logical = self.home / f"safe-state-{index}"
                logical.symlink_to(physical, target_is_directory=True)
                self.env["XDG_STATE_HOME"] = str(logical)
                proc = self.run_install("--skills-dir", str(self.skills), check=False)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("tabs or newlines", proc.stderr)
                self.assertEqual(list(physical.iterdir()), [])
                self.assertFalse(self.launcher.exists())
                self.assertFalse(self.skills.exists())
                if suffix.endswith("\n"):
                    self.assertFalse((self.home / suffix.rstrip("\n")).exists())


if __name__ == "__main__":
    unittest.main()
