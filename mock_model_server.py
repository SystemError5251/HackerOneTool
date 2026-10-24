#!/usr/bin/env python3
"""mock_model_server — a fake OpenAI-compatible model for testing the pipeline.

Lets you exercise the OpenCode integration (analyze.sh, the slash commands)
end-to-end without a real provider or API key. It implements the minimum of
the OpenAI chat API that OpenCode's AI SDK calls — `/v1/chat/completions`
(streaming and not) and `/v1/models` — and returns a deterministic, offline
"analysis" derived from the prompt it receives. It calls no external model and
makes no network requests; it only proves the plumbing works.

Usage:
    python3 mock_model_server.py            # listen on 127.0.0.1:8787
    python3 mock_model_server.py --port 9000

Then point OpenCode at the `mock` provider (see opencode.json) and run, e.g.:
    opencode run --model mock/mock-1 "hello"
"""
from __future__ import annotations

import argparse
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_ID = "mock-1"


def last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):  # content parts
                return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return ""


def build_reply(messages: list[dict]) -> str:
    """A canned but prompt-aware summary, so you can see data flowing through."""
    text = last_user_text(messages)
    data = text.split("--- DATA ---", 1)[-1] if "--- DATA ---" in text else text

    assets = sorted(set(re.findall(r"\b((?:\*\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/\*)?)\b", data)))[:10]
    tiers = sorted(set(re.findall(r"Tier \d", data)))
    sevs = sorted(set(re.findall(r"\b(critical|high|medium|low)\b", data, re.I)))

    lines = [
        "[mock model] This is a deterministic offline reply for pipeline testing.",
        "It does not use a real LLM — swap in a real provider for actual analysis.",
        "",
        f"- received ~{len(data.split())} words of injected data",
        f"- tiers seen: {', '.join(tiers) or 'none'}",
        f"- severities seen: {', '.join(sevs) or 'none'}",
    ]
    if assets:
        lines.append("- sample assets detected:")
        lines += [f"    - {a}" for a in assets]
    return "\n".join(lines)


def completion_payload(reply: str) -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": reply},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def chunk(delta: dict, finish=None) -> str:
    obj = {
        "id": "chatcmpl-mock",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(obj)}\n\n"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [
                {"id": MODEL_ID, "object": "model", "owned_by": "mock"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "invalid JSON"}})
            return

        reply = build_reply(req.get("messages", []))

        if req.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(chunk({"role": "assistant"}).encode())
            for word in reply.split(" "):
                self.wfile.write(chunk({"content": word + " "}).encode())
                self.wfile.flush()
            self.wfile.write(chunk({}, finish="stop").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            self._json(200, completion_payload(reply))


def main() -> int:
    ap = argparse.ArgumentParser(description="Fake OpenAI-compatible model server for testing.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mock model listening on http://{args.host}:{args.port}/v1  (model: mock/{MODEL_ID})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
