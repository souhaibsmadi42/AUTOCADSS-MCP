"""Drive the real server over its stdio pipe.

Regression test: on Windows the first tool call used to hang forever because
NumPy was imported lazily while stdin had a pending read. In-process tests
cannot see that, so this one spawns the server and enforces a hard deadline.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading

DEADLINE_SECONDS = 60


def _call(proc, replies, msg_id, method, params):
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}) + "\n")
    proc.stdin.flush()
    while True:
        try:
            reply = json.loads(replies.get(timeout=DEADLINE_SECONDS))
        except queue.Empty:
            raise AssertionError(f"server did not answer {method} within {DEADLINE_SECONDS}s") from None
        if reply.get("id") == msg_id:
            return reply


def _tool_payload(reply):
    return json.loads(reply["result"]["content"][0]["text"])


def test_tool_calls_return_over_stdio():
    env = dict(os.environ, AUTOCADSS_MCP_BACKEND="ezdxf")
    proc = subprocess.Popen(
        [sys.executable, "-m", "autocadss_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        env=env,
    )
    replies: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: [replies.put(line) for line in proc.stdout], daemon=True).start()

    try:
        _call(proc, replies, 1, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smoke", "version": "0"},
        })
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        status = _tool_payload(_call(proc, replies, 2, "tools/call", {
            "name": "system", "arguments": {"operation": "status"},
        }))
        assert status["ok"] is True
        assert status["payload"]["backend"] == "ezdxf"

        _call(proc, replies, 3, "tools/call", {
            "name": "entity",
            "arguments": {"operation": "create_line", "x1": 0, "y1": 0, "x2": 100, "y2": 50},
        })
        count = _tool_payload(_call(proc, replies, 4, "tools/call", {
            "name": "entity", "arguments": {"operation": "count"},
        }))
        assert count["ok"] is True
        assert "1" in json.dumps(count["payload"])
    finally:
        proc.kill()
        proc.wait(timeout=10)
