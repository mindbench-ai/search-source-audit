# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 MindBench.ai

"""Local editor for prompts.json and config.json.

A browser can't write to disk from a file:// page, which is why editing prompts
by hand meant downloading a file and moving it into place. This runs a small
local server instead: it serves the editor, hands it the current prompts and
config, and writes your changes straight back to the repo files.

    python3 src/configure.py

It opens http://127.0.0.1:8765 in your browser. The server is bound to localhost
only and writes just two files, prompts.json and config.json. Stop it with
Ctrl-C when you're done.
"""

from __future__ import annotations

import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paths
import providers

HOST = "127.0.0.1"
PORT = 8765
EDITOR = paths.REPO / "editor.html"


def _write_json(path, data) -> None:
    """Write pretty JSON, preserving unicode, via a temp file so a crash mid-write
    can't leave a half-written file behind."""
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _state() -> dict:
    return {
        "prompts": json.loads(paths.PROMPTS.read_text(encoding="utf-8")),
        "config": json.loads(paths.CONFIG.read_text(encoding="utf-8")),
        "providers": sorted(providers.PROVIDERS),
    }


def _save_prompts(prompts) -> tuple[int, str]:
    if not isinstance(prompts, list):
        return 400, "expected a list of prompts"
    for i, p in enumerate(prompts):
        if not isinstance(p, dict):
            return 400, f"prompt {i} is not an object"
        for field in ("prompt_id", "language", "topic", "variant", "text"):
            if not str(p.get(field, "")).strip():
                return 400, f"prompt {i} ({p.get('prompt_id') or '?'}) is missing {field}"
    ids = [p["prompt_id"] for p in prompts]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        return 400, f"duplicate prompt_id: {', '.join(sorted(dupes))}"
    _write_json(paths.PROMPTS, prompts)
    return 200, f"saved {len(prompts)} prompts to prompts.json"


# Only these keys are editable from the UI. Everything else in config.json
# (experiment, config_version, description, models definitions, _help) is left
# exactly as it was.
_CONFIG_SCALARS = ("dataset", "conditions", "runs_per_prompt", "workers", "max_cost_usd")


def _save_config(payload) -> tuple[int, str]:
    if not isinstance(payload, dict):
        return 400, "expected a config object"
    cfg = json.loads(paths.CONFIG.read_text(encoding="utf-8"))

    if "models" in payload:
        models = payload["models"]
        if not isinstance(models, dict) or not models:
            return 400, "at least one model must be defined"
        for key, spec in models.items():
            if spec.get("provider") not in providers.PROVIDERS:
                return 400, f"model '{key}' has unknown provider '{spec.get('provider')}'"
            if not str(spec.get("model_id", "")).strip():
                return 400, f"model '{key}' is missing model_id"
        cfg["models"] = models

    if "active_models" in payload:
        active = payload["active_models"]
        defined = cfg.get("models", {})
        unknown = [m for m in active if m not in defined]
        if unknown:
            return 400, f"active model(s) not defined: {', '.join(unknown)}"
        if not active:
            return 400, "at least one active model is required"
        cfg["active_models"] = active

    for key in _CONFIG_SCALARS:
        if key in payload:
            cfg[key] = payload[key]

    if not cfg.get("conditions"):
        return 400, "at least one condition is required"

    _write_json(paths.CONFIG, cfg)
    return 200, "saved config.json"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):  # quieter console
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html", "/editor.html"):
            self._send(200, EDITOR.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json(200, _state())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            self._json(400, {"ok": False, "message": f"bad JSON: {exc}"})
            return

        try:
            if self.path == "/api/prompts":
                code, msg = _save_prompts(payload)
            elif self.path == "/api/config":
                code, msg = _save_config(payload)
            else:
                code, msg = 404, "not found"
        except Exception as exc:  # noqa: BLE001 - report, don't crash the server
            code, msg = 500, f"{type(exc).__name__}: {exc}"

        self._json(code, {"ok": code == 200, "message": msg})


def main() -> None:
    if not EDITOR.exists():
        raise SystemExit(f"editor.html not found at {EDITOR}")
    url = f"http://{HOST}:{PORT}"
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"editing prompts.json and config.json in {paths.REPO}")
    print(f"open {url} (opening it for you now); Ctrl-C to stop")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001 - headless box, just print the URL
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
