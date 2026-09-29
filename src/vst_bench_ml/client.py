"""Synchronous client for the separately installed host JSON-RPC protocol."""

from __future__ import annotations

import json
import urllib.request


class TestHostError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(f"TestHost RPC error {code}: {message}")
        self.code = code
        self.message = message


# Request-framing / parse errors caused by truncated bodies — worth resending on
# a fresh connection. Application errors (e.g. -32002 "already loaded") are not.
_RETRYABLE_CODES = {-32600, -32700}


class TestHostClient:
    def __init__(
        self, host: str = "127.0.0.1", port: int = 8765, timeout: float = 120.0
    ):
        self.url = f"http://{host}:{port}"
        self.timeout = timeout
        self._id = 0

    def call(self, method: str, params: dict | None = None, tries: int = 3) -> dict:
        last_err = None
        for attempt in range(tries):
            self._id += 1
            payload = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params or {},
                    "id": self._id,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                self.url,
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json", "Connection": "close"},
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = json.loads(r.read().decode("utf-8"))
            except OSError as e:
                last_err = e  # connection/transport hiccup: retry
                continue
            if "error" in body:
                err = body["error"]
                exc = TestHostError(err.get("code", -1), err.get("message", "unknown"))
                if exc.code in _RETRYABLE_CODES and attempt < tries - 1:
                    last_err = exc  # truncated-body framing error: resend
                    continue
                raise exc  # application error — do not retry
            return body.get("result", {})
        raise last_err

    # ── lifecycle ────────────────────────────────────────────────
    def ping(self) -> bool:
        try:
            self.call("ping", tries=1)
            return True
        except (TestHostError, OSError):
            return False

    def load_plugin(self, plugin_path: str) -> dict:
        return self.call("load_plugin", {"plugin_path": plugin_path})

    def unload_plugin(self) -> dict:
        return self.call("unload_plugin")

    def ensure_plugin(self, plugin_path: str) -> dict:
        """Load the requested plugin and fail closed on incomplete identity."""
        try:
            self.load_plugin(plugin_path)
        except TestHostError as e:
            if e.code == -32002:
                raise TestHostError(
                    e.code, "host already has a plugin loaded; start a fresh host"
                ) from e
            raise
        identity = self.call("get_identity")
        host = identity.get("host") or {}
        plugin = identity.get("plugin") or {}
        required_host = {
            "protocol_version",
            "source_repository",
            "source_commit",
            "executable_sha256",
            "build_configuration",
        }
        missing = sorted(
            key
            for key in required_host
            if key not in host
            or host[key] is None
            or (isinstance(host[key], str) and not host[key].strip())
        )
        if missing:
            raise TestHostError(-32010, f"host identity missing: {', '.join(missing)}")
        required_plugin = {"path", "sha256", "format", "name", "vendor", "identifier"}
        missing = sorted(
            key
            for key in required_plugin
            if key not in plugin
            or plugin[key] is None
            or (isinstance(plugin[key], str) and not plugin[key].strip())
        )
        if missing:
            raise TestHostError(
                -32011, f"plugin identity missing: {', '.join(missing)}"
            )
        from pathlib import Path

        if str(Path(plugin_path).resolve()) != str(Path(plugin["path"]).resolve()):
            raise TestHostError(
                -32012, "loaded plugin path does not match requested path"
            )
        capabilities = identity.get("capabilities") or {}
        if not capabilities.get("deterministic_reset") or not capabilities.get(
            "parameter_readback"
        ):
            raise TestHostError(-32013, "host lacks reset/readback capability")
        return {
            "host": host,
            "plugin": plugin,
            "plugin_identifier": plugin["identifier"],
        }

    # ── parameters ───────────────────────────────────────────────
    def list_parameters(self) -> list[dict]:
        return self.call("list_parameters").get("parameters", [])

    def set_parameters(self, values: list[dict]) -> dict:
        """Apply a batch of ``{"index", "value"}`` (value normalized 0..1)."""
        return self.call("set_parameters", {"parameters": values})

    def get_plugin_state(self) -> dict:
        return self.call("get_plugin_state")

    def set_plugin_state(self, state_base64: str) -> dict:
        return self.call("set_plugin_state", {"state_base64": state_base64})

    # ── render ───────────────────────────────────────────────────
    def render_audio(
        self, num_samples: int, output_path: str, midi_events: list[dict]
    ) -> dict:
        return self.call(
            "render_audio",
            {
                "num_samples": num_samples,
                "output_path": output_path,
                "midi_events": midi_events,
            },
        )
