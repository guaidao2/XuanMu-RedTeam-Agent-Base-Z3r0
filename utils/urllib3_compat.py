"""Compatibility fixes for urllib3 quirks in third-party streaming clients."""

from __future__ import annotations

import io

from urllib3.response import HTTPResponse


_PATCHED_ATTR = "_z3r0_closed_file_close_patch"


def install_urllib3_closed_file_close_patch() -> None:
    if getattr(HTTPResponse, _PATCHED_ATTR, False):
        return

    original_close = HTTPResponse.close

    def close(self: HTTPResponse) -> None:
        try:
            original_close(self)
        except ValueError as exc:
            if str(exc) != "I/O operation on closed file.":
                raise
            connection = getattr(self, "_connection", None)
            if connection:
                connection.close()
            self._fp = None
            if not getattr(self, "auto_close", True):
                io.IOBase.close(self)

    setattr(HTTPResponse, "close", close)
    setattr(HTTPResponse, _PATCHED_ATTR, True)
