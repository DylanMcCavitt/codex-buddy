import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".codex" / "hooks" / "codex_buddy_hook.py"


class CaptureHandler(BaseHTTPRequestHandler):
    payloads = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.__class__.payloads.append(json.loads(raw.decode("utf-8")))
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        return


class HookScriptTests(unittest.TestCase):
    def test_forwards_enveloped_payload(self):
        CaptureHandler.payloads = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = os.environ.copy()
            env["CODEX_BUDDY_HOOK_URL"] = f"http://127.0.0.1:{server.server_port}/hook"
            proc = subprocess.run(
                [sys.executable, str(HOOK)],
                input=json.dumps({"hook_event_name": "SessionStart"}),
                text=True,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(proc.returncode, 0)
        self.assertEqual(len(CaptureHandler.payloads), 1)
        self.assertEqual(CaptureHandler.payloads[0]["hook"]["hook_event_name"], "SessionStart")
        self.assertIn("received_at", CaptureHandler.payloads[0])

    def test_missing_daemon_still_exits_zero(self):
        env = os.environ.copy()
        env["CODEX_BUDDY_HOOK_URL"] = "http://127.0.0.1:9/hook"
        env["CODEX_BUDDY_HOOK_TIMEOUT"] = "0.05"
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"hook_event_name": "UserPromptSubmit"}),
            text=True,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )

        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
