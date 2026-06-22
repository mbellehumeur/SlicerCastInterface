"""Image Display Client Cast request handlers (status-request)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, TYPE_CHECKING

from .cast_client import (
    data_type_from_event_name,
    hub_event_name,
    is_request_event,
    normalize_data_type,
    request_context,
)

if TYPE_CHECKING:
    from .cast_client import SlicerCastClient
    from .image_display_client_hub import ImageDisplayClientConnection

LOGGER = logging.getLogger("CastInterface.ImageDisplay")

_DEFAULT_DISPLAY_PRODUCT_NAME = "3DSLICER-ID"

EMPTY_FHIRCAST_CONTEXT: Dict[str, Any] = {"context.type": "", "context": []}
ID_ACTOR_KEYWORD = "ID"
STATUS_DATA_TYPE = "STATUS"
SCENEVIEW_BUILD_TIMEOUT_SECONDS = 9.0


def _normalize_target_actor(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().upper()
    return ""


def _accepts_inbound_target(message: Dict[str, Any]) -> bool:
    target = message.get("target.actor")
    if target is None:
        return True
    keyword = _normalize_target_actor(target)
    if not keyword or keyword == "*":
        return True
    return keyword == ID_ACTOR_KEYWORD


def _accepts_target_product(message: Dict[str, Any], product_name: str) -> bool:
    target_product = message.get("target.product.name")
    if target_product is None:
        return True
    text = str(target_product).strip()
    if not text or text == "*":
        return True
    expected = (product_name or _DEFAULT_DISPLAY_PRODUCT_NAME).strip()
    return text.upper() == expected.upper()


def _request_correlation_id(message: Dict[str, Any]) -> str:
    context = request_context(message)
    correlation_id = context.get("id")
    if isinstance(correlation_id, str) and correlation_id.strip():
        return correlation_id.strip()
    return ""


def _request_data_type(message: Dict[str, Any], hub_event: str) -> str:
    context = request_context(message)
    data_type = context.get("dataType")
    if isinstance(data_type, str) and data_type.strip():
        return data_type.strip()
    return data_type_from_event_name(hub_event)


def _resolve_product_name(connection: "ImageDisplayClientConnection") -> str:
    name = (connection.get_product_name() or "").strip()
    if name:
        return name
    client = connection.get_client()
    if client is not None:
        session_name = (client._session_cfg.product_name or "").strip()
        if session_name:
            return session_name
    return _DEFAULT_DISPLAY_PRODUCT_NAME


def _topic_from_message(message: Dict[str, Any]) -> Any:
    event = message.get("event") or {}
    return event.get("hub.topic")


async def handle_status_request(
    connection: "ImageDisplayClientConnection",
    client: "SlicerCastClient",
    message: Dict[str, Any],
) -> None:
    correlation_id = _request_correlation_id(message)
    if not correlation_id:
        LOGGER.info("Ignoring status-request: missing context.id")
        return

    product_name = _resolve_product_name(connection)
    open_context = connection.get_last_open_context()

    def build_sceneview(*, fast_placeholder_thumbnails: bool = False) -> Dict[str, Any]:
        from .build_sceneview_response import build_sceneview_response_payload

        return build_sceneview_response_payload(
            product_name,
            open_context,
            fast_placeholder_thumbnails=fast_placeholder_thumbnails,
        )

    try:
        sceneview = await asyncio.wait_for(
            connection.run_on_main_thread(lambda: build_sceneview()),
            timeout=SCENEVIEW_BUILD_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        LOGGER.error(
            "status sceneview build timed out after %.0fs; sending placeholder thumbnails",
            SCENEVIEW_BUILD_TIMEOUT_SECONDS,
        )
        sceneview = await connection.run_on_main_thread(
            lambda: build_sceneview(fast_placeholder_thumbnails=True)
        )

    payload = {
        "source": "status",
        "product": product_name,
        "items": [{"key": "availability", "value": "online"}],
        "sceneview": sceneview,
    }
    client.send_cast_request_response(
        correlation_id,
        STATUS_DATA_TYPE,
        payload,
        _topic_from_message(message),
    )
    viewports = sceneview.get("viewports") if isinstance(sceneview, dict) else []
    LOGGER.info(
        "sent status-response id=%s viewportCount=%d",
        correlation_id,
        len(viewports) if isinstance(viewports, list) else 0,
    )


async def handle_cast_request(
    connection: "ImageDisplayClientConnection",
    client: "SlicerCastClient",
    message: Dict[str, Any],
) -> None:
    hub_event = hub_event_name(message)
    if not is_request_event(hub_event):
        return

    if not _accepts_inbound_target(message):
        LOGGER.info(
            "Ignoring %s: target actor mismatch (%s)",
            hub_event,
            message.get("target.actor"),
        )
        return

    product_name = _resolve_product_name(connection)
    if not _accepts_target_product(message, product_name):
        LOGGER.info(
            "Ignoring %s: target product mismatch (%s)",
            hub_event,
            message.get("target.product.name"),
        )
        return

    data_type = _request_data_type(message, hub_event)
    normalized = normalize_data_type(data_type)

    if normalized == normalize_data_type(STATUS_DATA_TYPE):
        await handle_status_request(connection, client, message)
        return

    LOGGER.debug(
        "Ignoring unsupported request event=%s dataType=%s",
        hub_event,
        data_type,
    )
