"""Upstox V3 Market Data Feed Protobuf Decoder.

Decodes raw binary WebSocket frames into official Upstox V3 FeedResponse Protobuf instances.
Fails closed immediately on malformed, incomplete, or corrupted frames.
"""

from __future__ import annotations

from typing import Union

from engine.data.feeds.upstox.proto import market_data_feed_pb2

__all__ = [
    "UpstoxDecodeError",
    "UpstoxV3Decoder",
]

BinaryPayload = Union[bytes, bytearray, memoryview]


class UpstoxDecodeError(ValueError):
    """Raised when decoding a raw binary protobuf frame fails."""


class UpstoxV3Decoder:
    """Decoder for Upstox Market Data Feed V3 Protobuf binary frames."""

    def decode(self, raw_payload: BinaryPayload) -> market_data_feed_pb2.FeedResponse:
        """Parse raw binary protobuf bytes into a FeedResponse message.

        Args:
            raw_payload: Binary data received from the WebSocket connection.

        Returns:
            Decoded FeedResponse instance.

        Raises:
            TypeError: If raw_payload is not bytes-like.
            UpstoxDecodeError: If raw_payload is empty or cannot be parsed as a valid FeedResponse.
        """
        if not isinstance(raw_payload, (bytes, bytearray, memoryview)):
            raise TypeError(
                f"raw_payload must be bytes, bytearray, or memoryview, got {type(raw_payload).__name__}"
            )

        payload_bytes = bytes(raw_payload)
        if len(payload_bytes) == 0:
            raise UpstoxDecodeError("Empty payload cannot be decoded as FeedResponse")

        response = market_data_feed_pb2.FeedResponse()
        try:
            response.ParseFromString(payload_bytes)
        except Exception as exc:
            raise UpstoxDecodeError(f"Malformed Upstox V3 Protobuf payload: {exc}") from exc

        return response
