from fastapi import APIRouter, Depends, Query

from handler.egress_proxy.proxies import (
    create_egress_proxy_handler,
    delete_egress_proxy_handler,
    query_egress_proxies_handler,
    test_egress_proxy_handler,
    update_egress_proxy_handler,
)
from middleware.auth import require_admin
from router.common.responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES, not_found_response
from schema.common.responses import CommonResponse
from schema.egress_proxy.proxies import (
    DeleteEgressProxyResponse,
    EgressProxySchema,
    QueryEgressProxiesResponse,
    TestEgressProxyResponse,
)


NOT_FOUND_RESPONSE = not_found_response("Egress proxy")
ADMIN_ONLY = [Depends(require_admin)]

router = APIRouter(prefix="/egress-proxies", tags=["egress-proxies"])


async def query_egress_proxies_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=100),
    keyword: str = Query(default=""),
) -> CommonResponse[QueryEgressProxiesResponse]:
    return await query_egress_proxies_handler(page=page, size=size, keyword=keyword)


router.add_api_route(
    "",
    create_egress_proxy_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[EgressProxySchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE},
)

router.add_api_route(
    "/{id}",
    update_egress_proxy_handler,
    methods=["PATCH"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[EgressProxySchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}",
    delete_egress_proxy_handler,
    methods=["DELETE"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[DeleteEgressProxyResponse],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/test",
    test_egress_proxy_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[TestEgressProxyResponse],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "",
    query_egress_proxies_route,
    methods=["GET"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[QueryEgressProxiesResponse],
    responses=COMMON_ERROR_RESPONSES,
)
