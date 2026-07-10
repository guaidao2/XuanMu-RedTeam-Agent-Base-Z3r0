from schema.common.responses import CommonResponse


# 401 / 403 are now driven from the route's auth dependencies; this dict only
# carries shared error responses that have to be declared per-route
COMMON_ERROR_RESPONSES = {
    422: {"description": "Validation Error", "model": CommonResponse},
}

BAD_REQUEST_RESPONSE = {
    400: {"description": "Bad Request", "model": CommonResponse},
}

INTERNAL_ERROR_RESPONSE = {
    500: {"description": "Internal Server Error", "model": CommonResponse},
}

CONFLICT_RESPONSE = {
    409: {"description": "Conflict", "model": CommonResponse},
}


def not_found_response(resource: str) -> dict:
    return {404: {"description": f"{resource} not found", "model": CommonResponse}}
