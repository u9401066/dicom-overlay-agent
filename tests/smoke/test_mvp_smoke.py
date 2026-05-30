from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
import websockets
from tests.unit.test_agent import MockScreenMonitor

from dicom_overlay.application.overlay_agent import OverlayAgent
from dicom_overlay.domain.entities import AppConfig, TriggerMode, WindowRect
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from dicom_overlay.infrastructure.region_mapper import RegionMapper
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mvp_smoke_pipeline() -> None:
    received_messages: list[dict[str, Any]] = []

    async def handler(websocket):
        connect_raw = await websocket.recv()
        connect_request = json.loads(connect_raw)
        received_messages.append(connect_request)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": connect_request["id"],
                    "ok": True,
                    "payload": {"status": "ok"},
                }
            )
        )

        chat_raw = await websocket.recv()
        chat_request = json.loads(chat_raw)
        received_messages.append(chat_request)
        run_id = str(uuid4())
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": chat_request["id"],
                    "ok": True,
                    "payload": {
                        "status": "accepted",
                        "runId": run_id,
                    },
                }
            )
        )
        await websocket.send(
            json.dumps(
                {
                    "type": "event",
                    "event": "chat",
                    "payload": {
                        "runId": run_id,
                        "sessionKey": "main",
                        "seq": 1,
                        "state": "final",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(
                                        {
                                            "modality": "EKG",
                                            "analysis_time_ms": 42,
                                            "summary": "Smoke test summary",
                                            "severity": "warning",
                                            "model_used": "smoke-model",
                                            "findings": [
                                                {
                                                    "id": "f1",
                                                    "regions": ["lead_I"],
                                                    "label": "Smoke",
                                                    "detail": "Smoke detail",
                                                    "severity": "warning",
                                                }
                                            ],
                                            "checklist": {
                                                "rate": {"value": "72", "status": "normal"}
                                            },
                                        }
                                    ),
                                }
                            ],
                        },
                    },
                }
            )
        )

    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        config = AppConfig()
        config.analysis.trigger_mode = TriggerMode.AUTO
        config.openclaw.gateway_url = f"ws://127.0.0.1:{port}"
        config.monitor.debounce_stable_sec = 0.0
        config.region_maps = {
            "EKG": {
                "layout": "standard_4x3",
                "regions": {
                    "lead_I": {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.27}
                },
            }
        }

        screen_monitor = MockScreenMonitor()
        screen_monitor.window = WindowRect(left=0, top=0, width=1000, height=800)
        screen_monitor.hash_value = "1111111111111111"

        image_processor = ImageProcessor()
        region_mapper = RegionMapper(config.region_maps)
        vision_client = OpenClawClient(gateway_url=config.openclaw.gateway_url)

        agent = OverlayAgent(
            config=config,
            screen_monitor=screen_monitor,
            image_processor=image_processor,
            vision_analyzer=vision_client,
            region_mapper=region_mapper,
        )

        results: list[Any] = []
        errors: list[str] = []
        agent.on_analysis_result = results.append
        agent.on_error = errors.append

        await agent.start()
        await agent.tick()

        screen_monitor.hash_changed = True
        await agent.tick()
        await agent.tick()

        assert received_messages
        assert received_messages[0]["method"] == "connect"
        assert received_messages[1]["method"] == "chat.send"
        payload = received_messages[1]["params"]
        assert payload["sessionKey"] == "main"
        assert payload["attachments"][0]["type"] == "image"
        assert results
        assert results[0].summary == "Smoke test summary"
        assert results[0].model_used == "smoke-model"
        assert not errors
    finally:
        server.close()
        await server.wait_closed()
