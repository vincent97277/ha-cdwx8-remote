"""Read CDWX8 button frames in their original advertisement byte order."""

from collections.abc import Iterator
from uuid import UUID

from bluetooth_data_tools import parse_advertisement_data_bytes

from .const import BUTTON_EVENTS


def press_frames(raw: bytes | None) -> Iterator[bytes]:
    """Yield 128-bit service UUIDs that contain a supported key code."""
    if not raw:
        return
    _, service_uuids, _, _, _ = parse_advertisement_data_bytes(raw)
    for service_uuid in service_uuids:
        frame = UUID(service_uuid).bytes[::-1]
        if 1 <= frame[7] <= len(BUTTON_EVENTS):
            yield frame
