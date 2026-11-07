r"""Protocol-level smoke test for mcp_server.py.

Speaks raw JSON-RPC over stdio — exactly what any MCP client does — so a pass
here means the server is usable by Claude Desktop, Cursor, Cline, or anything
else that implements the spec, not just by us.

    .\.venv\Scripts\python.exe tools\mcp_smoke.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "mcp_server.py")
PYTHON = sys.executable


class Client:
    def __init__(self):
        self.proc = subprocess.Popen(
            [PYTHON, SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=ROOT, text=True, encoding="utf-8", bufsize=1,
        )
        self._id = 0

    def send(self, payload: dict):
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def read(self) -> dict:
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read()
            raise RuntimeError("server closed stdout: " + err[:500])
        return json.loads(line)

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self.send({"jsonrpc": "2.0", "id": self._id, "method": method,
                   "params": params or {}})
        while True:
            msg = self.read()
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg["result"]

    def notify(self, method: str):
        self.send({"jsonrpc": "2.0", "method": method})

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def main() -> int:
    c = Client()
    try:
        init = c.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "probridge-smoke", "version": "1.0"},
        })
        info = init.get("serverInfo", {})
        print(f"  PASS  initialize      {info.get('name')} {info.get('version')} "
              f"protocol={init.get('protocolVersion')}")

        c.notify("notifications/initialized")

        tools = c.request("tools/list").get("tools", [])
        print(f"  PASS  tools/list      {len(tools)} tools")
        for t in tools:
            required = t.get("inputSchema", {}).get("required", [])
            print(f"          {t['name']:22s} required={required}")

        ping = c.request("tools/call", {"name": "pro_ping", "arguments": {}})
        text = ping["content"][0]["text"]
        data = json.loads(text)
        ok = data.get("ok")
        print(f"  PASS  pro_ping        ok={ok} "
              f"project={(data.get('data') or {}).get('project')}")
        if not ok:
            print(f"          note: {data.get('error')}")

        layers = c.request("tools/call", {"name": "pro_list_layers", "arguments": {}})
        payload = json.loads(layers["content"][0]["text"])
        print(f"  PASS  pro_list_layers ok={payload.get('ok')}")

        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  {exc}")
        return 1
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
