import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from codex_buddy_bridge.launch_agent import (
    LaunchAgentPaths,
    bootstrap,
    bootout_command,
    bootstrap_command,
    build_config,
    kickstart_command,
    print_command,
    program_arguments,
    remove_plist,
    render_plist,
    service_target,
    user_domain,
    write_plist,
)


class LaunchAgentPlistTests(unittest.TestCase):
    def test_render_plist_runs_serial_bridge_with_predictable_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            config = build_config(
                python="/opt/codex/python",
                source_dir=Path("/repo/src"),
                paths=paths,
            )

            body = plistlib.loads(render_plist(config))

        self.assertEqual(body["Label"], "com.codex-buddy.bridge")
        self.assertEqual(body["ProgramArguments"], list(program_arguments(config)))
        self.assertEqual(
            body["ProgramArguments"],
            [
                "/opt/codex/python",
                "-m",
                "codex_buddy_bridge",
                "bridge",
                "--host",
                "127.0.0.1",
                "--port",
                "47833",
                "--serial",
            ],
        )
        self.assertTrue(body["RunAtLoad"])
        self.assertTrue(body["KeepAlive"])
        self.assertEqual(body["ProcessType"], "Background")
        self.assertEqual(body["StandardOutPath"], str(paths.log_path))
        self.assertEqual(body["StandardErrorPath"], str(paths.error_log_path))
        self.assertEqual(body["EnvironmentVariables"]["PYTHONPATH"], "/repo/src")
        self.assertEqual(body["EnvironmentVariables"]["CODEX_BUDDY_LOG_PATH"], str(paths.log_path))
        self.assertEqual(body["EnvironmentVariables"]["CODEX_BUDDY_LOG_STDOUT_ONLY"], "1")

    def test_serial_port_overrides_auto_discovery_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = build_config(
                python="/opt/codex/python",
                source_dir=Path("/repo/src"),
                serial_port="/dev/cu.usbserial-7552A41038",
                paths=self._paths(Path(tmp)),
            )

            args = program_arguments(config)

        self.assertIn("--serial-port", args)
        self.assertIn("/dev/cu.usbserial-7552A41038", args)
        self.assertNotIn("--serial", args)

    def test_write_plist_is_idempotent_and_dry_run_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = build_config(
                python="/opt/codex/python",
                source_dir=Path("/repo/src"),
                paths=self._paths(Path(tmp)),
            )

            dry_run = write_plist(config, dry_run=True)
            self.assertTrue(dry_run.changed)
            self.assertFalse(dry_run.path.exists())

            first = write_plist(config)
            second = write_plist(config)

            self.assertTrue(first.changed)
            self.assertTrue(first.path.exists())
            self.assertFalse(second.changed)

    def test_remove_plist_deletes_only_the_installed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = build_config(
                python="/opt/codex/python",
                source_dir=Path("/repo/src"),
                paths=self._paths(Path(tmp)),
            )
            write_plist(config)

            result = remove_plist(config)

            self.assertTrue(result.changed)
            self.assertFalse(config.paths.plist_path.exists())

    def test_launchctl_commands_target_user_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = build_config(paths=self._paths(Path(tmp)))

            self.assertEqual(user_domain(uid=501), "gui/501")
            self.assertEqual(service_target(uid=501), "gui/501/com.codex-buddy.bridge")
            self.assertEqual(
                bootstrap_command(config, uid=501),
                ("launchctl", "bootstrap", "gui/501", str(config.paths.plist_path)),
            )
            self.assertEqual(
                bootout_command(config, uid=501),
                ("launchctl", "bootout", "gui/501/com.codex-buddy.bridge"),
            )
            self.assertEqual(
                kickstart_command(config, uid=501),
                ("launchctl", "kickstart", "-k", "gui/501/com.codex-buddy.bridge"),
            )
            self.assertEqual(
                print_command(config, uid=501),
                ("launchctl", "print", "gui/501/com.codex-buddy.bridge"),
            )

    def test_bootstrap_retries_transient_launchctl_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = build_config(paths=self._paths(Path(tmp)))
            calls = []

            def runner(command):
                calls.append(tuple(command))
                if len(calls) == 1:
                    return subprocess.CompletedProcess(command, 5, stdout="", stderr="Bootstrap failed")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            bootstrap(config, runner=runner, attempts=2, delay=0)

            self.assertEqual(calls, [bootstrap_command(config), bootstrap_command(config)])

    def _paths(self, root: Path) -> LaunchAgentPaths:
        runtime_dir = root / ".codex-buddy"
        return LaunchAgentPaths(
            plist_path=root / "Library" / "LaunchAgents" / "com.codex-buddy.bridge.plist",
            runtime_dir=runtime_dir,
            log_path=runtime_dir / "bridge.log",
            error_log_path=runtime_dir / "bridge.err.log",
        )


if __name__ == "__main__":
    unittest.main()
