"""Sandbox services."""


def close_docker_response_sync(socket: object, response: object | None) -> None:
    """Close a Docker API response attached to a socket, suppressing errors."""
    if response is None:
        response = getattr(socket, "_response", None)

    close = getattr(response, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass

    if response is not None:
        try:
            if getattr(socket, "_response", None) is response:
                setattr(socket, "_response", None)
        except Exception:
            pass
