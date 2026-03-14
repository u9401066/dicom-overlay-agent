"""Minimal real-gateway test - prints only final result."""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import sys
import time
import zlib
from pathlib import Path
from uuid import uuid4

import websockets


def _print(msg: str) -> None:
    print(msg, flush=True)


def _make_tiny_png() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
    raw = b"\x00\xff\xff\xff"
    idat_data = zlib.compress(raw)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF)
    idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + idat_crc
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + iend_crc
    return sig + ihdr + idat + iend


def _load_token() -> str:
    for name in ["openclaw/openclaw.json", "openclaw/openclaw.valid.json"]:
        p = Path(name)
        if p.exists():
            cfg = json.loads(p.read_text())
            t = cfg.get("gateway", {}).get("auth", {}).get("token", "")
            if t:
                return t
    raise RuntimeError("No gateway token found")


async def main() -> None:
    token = _load_token()
    img_b64 = base64.b64encode(_make_tiny_png()).decode()

    ws = await websockets.connect("ws://127.0.0.1:18789")
    cid = "c-1"
    await ws.send(
        json.dumps(
            {
                "type": "req",
                "id": cid,
                "method": "connect",
                "params": {
                    "minProtocol": 3,
                    "maxProtocol": 3,
                    "client": {"id": "cli", "version": "2026.3.11", "platform": "win", "mode": "cli"},
                    "role": "operator",
                    "scopes": ["operator.admin", "operator.read", "operator.write", "operator.approvals", "operator.pairing"],
                    "auth": {"token": token},
                },
            }
        )
    )

    # Wait for connect response
    while True:
        r = json.loads(await asyncio.wait_for(ws.recv(), 10))
        if r.get("type") == "res" and r.get("id") == cid:
            if not r.get("ok"):
                _print("CONNECT FAILED")
                return
            _print("[OK] Connected to Gateway")
            break

    # chat.send
    await ws.send(
        json.dumps(
            {
                "type": "req",
                "id": "chat-1",
                "method": "chat.send",
                "params": {
                    "sessionKey": "main",
                    "message": (
                        "Analyze this EKG image. Return ONLY a JSON object with keys: "
                        "modality, summary, severity, model_used, findings (array), "
                        "checklist (object). No markdown."
                    ),
                    "attachments": [{"type": "image", "mimeType": "image/png", "content": img_b64}],
                    "idempotencyKey": str(uuid4()),
                },
            }
        )
    )

    _print("[OK] chat.send dispatched, waiting for AI response...")
    t0 = time.time()
    event_count = 0

    while time.time() - t0 < 120:
        raw = await asyncio.wait_for(ws.recv(), 120)
        frame = json.loads(raw)
        ft = frame.get("type")

        if ft == "event":
            payload = frame.get("payload", {})
            state = payload.get("state", "")
            event_count += 1

            if state == "final":
                msg = payload.get("message", {})
                for c in msg.get("content", []):
                    if c.get("type") == "text":
                        text = c["text"]
                        _print(f"\n[FINAL] ({len(text)} chars, {event_count} events)")
                        _print("=" * 60)
                        _print(text)
                        _print("=" * 60)
                        # Also save to file for reliable capture
                        result_path = Path(__file__).parent / "real_result.json"
                        result_path.write_text(
                            json.dumps({"text": text, "chars": len(text), "events": event_count}, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        _print(f"[SAVED] {result_path}")
                break
            elif state == "error":
                err_msg = payload.get("errorMessage", "unknown")
                _print(f"\n[ERROR] {err_msg}")
                break

        elif ft == "res":
            if not frame.get("ok"):
                err = frame.get("error", {})
                _print(f"\n[RES ERROR] {err.get('code', '?')}: {err.get('message', '?')}")
                break

    elapsed = time.time() - t0
    _print(f"\n[DONE] elapsed={elapsed:.1f}s")
    await ws.close()


if __name__ == "__main__":
    asyncio.run(main())
