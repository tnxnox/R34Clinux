from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call
import subprocess

from r34_client.api.flaresolverr.launcher import (
    detect_container_cmd,
    is_url_local,
    _probe_flaresolverr,
    _is_container_running,
    restart_flaresolverr_container,
    start_flaresolverr_container,
    _run_new_container,
    _wait_for_flaresolverr,
)


class FlareSolverrLauncherTests(unittest.TestCase):
    @patch("r34_client.api.flaresolverr.launcher.shutil.which")
    @patch("r34_client.api.flaresolverr.launcher.subprocess.run")
    def test_detect_container_cmd_podman(self, mock_run: MagicMock, mock_which: MagicMock) -> None:
        mock_which.side_effect = lambda x: "/usr/bin/podman" if x == "podman" else None
        cmd = detect_container_cmd()
        self.assertEqual(cmd, ["podman"])
        mock_run.assert_not_called()

    @patch("r34_client.api.flaresolverr.launcher.shutil.which")
    @patch("r34_client.api.flaresolverr.launcher.subprocess.run")
    def test_detect_container_cmd_docker_direct(self, mock_run: MagicMock, mock_which: MagicMock) -> None:
        mock_which.side_effect = lambda x: "/usr/bin/docker" if x == "docker" else None
        # docker info succeeds
        mock_run.return_value = MagicMock(returncode=0)
        
        cmd = detect_container_cmd()
        self.assertEqual(cmd, ["docker"])
        # Should check docker info
        mock_run.assert_called_once()
        self.assertIn("docker", mock_run.call_args[0][0])
        self.assertIn("info", mock_run.call_args[0][0])

    @patch("r34_client.api.flaresolverr.launcher.shutil.which")
    @patch("r34_client.api.flaresolverr.launcher.subprocess.run")
    def test_detect_container_cmd_docker_sudo(self, mock_run: MagicMock, mock_which: MagicMock) -> None:
        mock_which.side_effect = lambda x: "/usr/bin/docker" if x == "docker" else None
        # docker info fails, but sudo docker info succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1), # normal
            MagicMock(returncode=0), # sudo
        ]
        
        cmd = detect_container_cmd()
        self.assertEqual(cmd, ["sudo", "-n", "docker"])
        self.assertEqual(mock_run.call_count, 2)

    @patch("r34_client.api.flaresolverr.launcher.shutil.which")
    def test_detect_container_cmd_none(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        cmd = detect_container_cmd()
        self.assertIsNone(cmd)

    def test_is_url_local(self) -> None:
        self.assertTrue(is_url_local("http://localhost:8191"))
        self.assertTrue(is_url_local("https://127.0.0.1/status"))
        self.assertTrue(is_url_local("http://[::1]:8191"))
        self.assertFalse(is_url_local("http://google.com"))
        self.assertFalse(is_url_local("not a url"))

    @patch("r34_client.api.flaresolverr.launcher.requests.get")
    def test_probe_flaresolverr_health_success(self, mock_get: MagicMock) -> None:
        mock_get.return_value = MagicMock(status_code=200)
        self.assertTrue(_probe_flaresolverr("http://localhost:8191"))
        # Should stop at /health
        self.assertEqual(mock_get.call_count, 1)

    @patch("r34_client.api.flaresolverr.launcher.requests.get")
    def test_probe_flaresolverr_root_fallback(self, mock_get: MagicMock) -> None:
        import requests
        mock_get.side_effect = [
            requests.RequestException("conn refused"), # /health fails
            MagicMock(status_code=200) # / succeeds
        ]
        self.assertTrue(_probe_flaresolverr("http://localhost:8191"))
        self.assertEqual(mock_get.call_count, 2)

    @patch("r34_client.api.flaresolverr.launcher.requests.get")
    def test_probe_flaresolverr_all_fail(self, mock_get: MagicMock) -> None:
        import requests
        mock_get.side_effect = requests.RequestException("conn refused")
        self.assertFalse(_probe_flaresolverr("http://localhost:8191"))
        self.assertEqual(mock_get.call_count, 2)

    @patch("r34_client.api.flaresolverr.launcher.subprocess.run")
    def test_is_container_running(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(stdout="some-other-container\nr34-flaresolverr\n")
        self.assertTrue(_is_container_running(["docker"], "r34-flaresolverr"))

        mock_run.return_value = MagicMock(stdout="some-other-container\n")
        self.assertFalse(_is_container_running(["docker"], "r34-flaresolverr"))

        mock_run.side_effect = Exception("failed to run")
        self.assertFalse(_is_container_running(["docker"], "r34-flaresolverr"))

    @patch("r34_client.api.flaresolverr.launcher._probe_flaresolverr")
    def test_restart_flaresolverr_container_remote(self, mock_probe: MagicMock) -> None:
        mock_probe.return_value = True
        res = restart_flaresolverr_container("http://remote-server:8191")
        self.assertTrue(res)
        mock_probe.assert_called_once_with("http://remote-server:8191")

    @patch("r34_client.api.flaresolverr.launcher.detect_container_cmd")
    def test_restart_flaresolverr_container_local_no_runtime(self, mock_detect: MagicMock) -> None:
        mock_detect.return_value = None
        res = restart_flaresolverr_container("http://127.0.0.1:8191")
        self.assertFalse(res)

    @patch("r34_client.api.flaresolverr.launcher.detect_container_cmd")
    @patch("r34_client.api.flaresolverr.launcher._is_container_running")
    @patch("r34_client.api.flaresolverr.launcher.subprocess.run")
    @patch("r34_client.api.flaresolverr.launcher._wait_for_flaresolverr")
    def test_restart_flaresolverr_container_running(
        self, mock_wait: MagicMock, mock_run: MagicMock, mock_running: MagicMock, mock_detect: MagicMock
    ) -> None:
        mock_detect.return_value = ["docker"]
        mock_running.return_value = True
        mock_wait.return_value = True

        res = restart_flaresolverr_container("http://127.0.0.1:8191")
        self.assertTrue(res)
        # Verify restart command was run
        mock_run.assert_called_once_with(["docker", "restart", "r34-flaresolverr"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        mock_wait.assert_called_once_with("http://127.0.0.1:8191")

    @patch("r34_client.api.flaresolverr.launcher.detect_container_cmd")
    @patch("r34_client.api.flaresolverr.launcher._is_container_running")
    @patch("r34_client.api.flaresolverr.launcher.subprocess.run")
    @patch("r34_client.api.flaresolverr.launcher.start_flaresolverr_container")
    def test_restart_flaresolverr_container_failed_restart_recreates(
        self, mock_start: MagicMock, mock_run: MagicMock, mock_running: MagicMock, mock_detect: MagicMock
    ) -> None:
        mock_detect.return_value = ["docker"]
        mock_running.return_value = True
        # Restart fails
        mock_run.side_effect = [
            subprocess.SubprocessError("timeout"), # restart fails
            None, # rm success
        ]
        mock_start.return_value = True

        res = restart_flaresolverr_container("http://127.0.0.1:8191")
        self.assertTrue(res)
        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_any_call(["docker", "rm", "-f", "r34-flaresolverr"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        mock_start.assert_called_once_with("http://127.0.0.1:8191")

    @patch("r34_client.api.flaresolverr.launcher._probe_flaresolverr")
    def test_start_flaresolverr_container_already_running(self, mock_probe: MagicMock) -> None:
        mock_probe.return_value = True
        res = start_flaresolverr_container("http://127.0.0.1:8191")
        self.assertTrue(res)

    @patch("r34_client.api.flaresolverr.launcher._probe_flaresolverr")
    def test_start_flaresolverr_container_remote_unreachable(self, mock_probe: MagicMock) -> None:
        mock_probe.return_value = False
        res = start_flaresolverr_container("http://remote-server:8191")
        self.assertFalse(res)

    @patch("r34_client.api.flaresolverr.launcher._probe_flaresolverr")
    @patch("r34_client.api.flaresolverr.launcher.detect_container_cmd")
    def test_start_flaresolverr_container_no_runtime(self, mock_detect: MagicMock, mock_probe: MagicMock) -> None:
        mock_probe.return_value = False
        mock_detect.return_value = None
        res = start_flaresolverr_container("http://127.0.0.1:8191")
        self.assertFalse(res)

    @patch("r34_client.api.flaresolverr.launcher._probe_flaresolverr")
    @patch("r34_client.api.flaresolverr.launcher.detect_container_cmd")
    @patch("r34_client.api.flaresolverr.launcher.subprocess.run")
    @patch("r34_client.api.flaresolverr.launcher._wait_for_flaresolverr")
    def test_start_flaresolverr_container_exists_starts(
        self, mock_wait: MagicMock, mock_run: MagicMock, mock_detect: MagicMock, mock_probe: MagicMock
    ) -> None:
        mock_probe.return_value = False
        mock_detect.return_value = ["docker"]
        # ps command returns r34-flaresolverr exists
        mock_run.side_effect = [
            MagicMock(stdout="some-container\nr34-flaresolverr\n"), # ps
            None, # start
        ]
        mock_wait.return_value = True

        res = start_flaresolverr_container("http://127.0.0.1:8191")
        self.assertTrue(res)
        mock_run.assert_any_call(["docker", "start", "r34-flaresolverr"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        mock_wait.assert_called_once_with("http://127.0.0.1:8191")

    @patch("r34_client.api.flaresolverr.launcher._probe_flaresolverr")
    @patch("r34_client.api.flaresolverr.launcher.detect_container_cmd")
    @patch("r34_client.api.flaresolverr.launcher.subprocess.run")
    @patch("r34_client.api.flaresolverr.launcher._run_new_container")
    def test_start_flaresolverr_container_exists_start_fails_recreates(
        self, mock_run_new: MagicMock, mock_run: MagicMock, mock_detect: MagicMock, mock_probe: MagicMock
    ) -> None:
        mock_probe.return_value = False
        mock_detect.return_value = ["docker"]
        mock_run.side_effect = [
            MagicMock(stdout="r34-flaresolverr"), # ps
            subprocess.CalledProcessError(1, "start"), # start fails
            None, # rm
        ]
        mock_run_new.return_value = True

        res = start_flaresolverr_container("http://127.0.0.1:8191")
        self.assertTrue(res)
        mock_run.assert_any_call(["docker", "rm", "-f", "r34-flaresolverr"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        mock_run_new.assert_called_once()

    @patch("r34_client.api.flaresolverr.launcher.subprocess.run")
    @patch("r34_client.api.flaresolverr.launcher._wait_for_flaresolverr")
    def test_run_new_container_success(self, mock_wait: MagicMock, mock_run: MagicMock) -> None:
        mock_wait.return_value = True
        res = _run_new_container(["docker"], "latest-img", "fallback-img", "r34-flaresolverr", "http://127.0.0.1:8191")
        self.assertTrue(res)
        # Should pull image and run
        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_any_call(["docker", "pull", "latest-img"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        self.assertIn("run", mock_run.call_args[0][0])

    @patch("r34_client.api.flaresolverr.launcher.subprocess.run")
    @patch("r34_client.api.flaresolverr.launcher._wait_for_flaresolverr")
    def test_run_new_container_pull_fallback(self, mock_wait: MagicMock, mock_run: MagicMock) -> None:
        mock_wait.return_value = True
        # First pull fails, second pull (fallback) succeeds, run succeeds
        mock_run.side_effect = [
            Exception("latest fail"),
            None, # fallback pull success
            None, # run success
        ]
        res = _run_new_container(["docker"], "latest-img", "fallback-img", "r34-flaresolverr", "http://127.0.0.1:8191")
        self.assertTrue(res)
        self.assertEqual(mock_run.call_count, 3)
        mock_run.assert_any_call(["docker", "pull", "fallback-img"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)

    @patch("r34_client.api.flaresolverr.launcher.time.sleep")
    @patch("r34_client.api.flaresolverr.launcher._probe_flaresolverr")
    def test_wait_for_flaresolverr(self, mock_probe: MagicMock, mock_sleep: MagicMock) -> None:
        # Fails 2 times, then succeeds
        mock_probe.side_effect = [False, False, True]
        res = _wait_for_flaresolverr("http://127.0.0.1:8191")
        self.assertTrue(res)
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertEqual(mock_probe.call_count, 3)

    @patch("r34_client.api.flaresolverr.launcher.time.sleep")
    @patch("r34_client.api.flaresolverr.launcher._probe_flaresolverr")
    def test_wait_for_flaresolverr_timeout(self, mock_probe: MagicMock, mock_sleep: MagicMock) -> None:
        mock_probe.return_value = False
        res = _wait_for_flaresolverr("http://127.0.0.1:8191")
        self.assertFalse(res)
        self.assertEqual(mock_sleep.call_count, 30)
