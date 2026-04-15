"""Quick real-gateway integration test (manual run only)."""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import time
import zlib
from pathlib import Path
from uuid import uuid4

import websockets


def _make_tiny_png() -> bytes:
    """Generate a minimal valid 1x1 white PNG."""
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
            if isinstance(t, str) and t:
                return t
    raise RuntimeError("No gateway token found")


async def main() -> None:
    img_b64 = base64.b64encode(_make_tiny_png()).decode()
    token = _load_token()

    ws = await websockets.connect("ws://127.0.0.1:18789")
    print("[1] WS connected")

    # handshake
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
                    "client": {
                        "id": "cli",
                        "version": "2026.3.11",
                        "platform": "win",
                        "mode": "cli",
                    },
                    "role": "operator",
                    "scopes": [
                        "operator.admin",
                        "operator.read",
                        "operator.write",
                        "operator.approvals",
                        "operator.pairing",
                    ],
                    "auth": {"token": token},
                },
            }
        )
    )
    # Wait for connect response (skip challenge events)
    while True:
        r = json.loads(await asyncio.wait_for(ws.recv(), 10))
        print(f"[2] frame: type={r.get('type')} event={r.get('event', '')} ok={r.get('ok', '')}")
        if r.get("type") == "res" and r.get("id") == cid:
            if not r.get("ok"):
                err = r.get("error", {})
                print(f"  CONNECT ERROR: {err.get('code')} - {err.get('message')}")
                await ws.close()
                return
            print("[2] connect OK")
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
                        "Analyze this EKG image. Return a JSON object with keys: "
                        "modality, summary, severity, model_used, findings (array), "
                        "checklist (object). Return ONLY the JSON, no markdown."
                    ),
                    "attachments": [
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "content": img_b64,
                        }
                    ],
                    "idempotencyKey": str(uuid4()),
                },
            }
        )
    )

    print("[3] chat.send sent, waiting for events...")
    t0 = time.time()
    while time.time() - t0 < 120:
        raw = await asyncio.wait_for(ws.recv(), 120)
        frame = json.loads(raw)
        ft = frame.get("type")
        if ft == "res":
            ok = frame.get("ok")
            payload = frame.get("payload", {})
            status = payload.get("status", "")
            run_id = payload.get("runId", "")
            print(f"[res] ok={ok} status={status} runId={run_id}")
            if not ok:
                err = frame.get("error", {})
                print(f"  ERROR: {err.get('code')} - {err.get('message')}")
                break
        elif ft == "event":
            payload = frame.get("payload", {})
            state = payload.get("state", "")
            seq = payload.get("seq", "")
            print(f"[event] {frame.get('event')} state={state} seq={seq}")
            if state == "error":
                print(f"  ERROR: {payload.get('errorMessage', '')}")
                break
            if state == "final":
                msg = payload.get("message", {})
                content = msg.get("content", [])
                for c in content:
                    if c.get("type") == "text":
                        text = c.get("text", "")
                        print(f"[FINAL] text length={len(text)}")
                        print(text[:3000])
                break
        else:
            print(f"[{ft}] {json.dumps(frame)[:200]}")

    elapsed = time.time() - t0
    print(f"\n[DONE] elapsed={elapsed:.1f}s")
    await ws.close()


if __name__ == "__main__":
    asyncio.run(main())
