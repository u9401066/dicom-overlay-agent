from __future__ import annotations

import pytest

from dicom_overlay.__main__ import _configured_gateway
from dicom_overlay.domain.entities import AppConfig
from dicom_overlay.infrastructure.gateway_manager import GatewayManager


@pytest.mark.parametrize("port", [True, False, None, "18789", 1.5, 0, -1, 65536])
def test_manager_rejects_invalid_port_before_creating_state(tmp_path, port):
    with pytest.raises(ValueError, match="port must be an integer"):
        GatewayManager(repo_root=tmp_path, port=port)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
@pytest.mark.parametrize("port", [18789, 49152, 65535])
def test_managed_process_uses_the_configured_client_port(tmp_path, host, port):
    config = AppConfig()
    config.openclaw.gateway_url = f"ws://{host}:{port}"
    config.openclaw.gateway_start_timeout_sec = 90
    manager = _configured_gateway(tmp_path, config)
    assert manager._port == port
    assert manager._ready_timeout_sec == 90
    assert manager._repo_root == tmp_path.resolve()
    assert manager.is_running is False


@pytest.mark.parametrize(
    "url",
    [
        "ws://127.0.0.1",
        "ws://127.0.0.1:0",
        "ws://127.0.0.1:65536",
        "ws://127.0.0.1:not-a-port",
        "wss://localhost:18789",
        "ws://example.invalid:18789",
        "ws://0.0.0.0:18789",
        "ws://user:password@localhost:18789",
        "ws://localhost:18789/remote",
        "ws://localhost:18789?token=fixture",
        "ws://localhost:18789#fragment",
    ],
)
def test_managed_process_rejects_ambiguous_or_external_endpoints(tmp_path, url):
    config = AppConfig()
    config.openclaw.gateway_url = url
    with pytest.raises(ValueError):
        _configured_gateway(tmp_path, config)
    assert not (tmp_path / "openclaw-home").exists()
