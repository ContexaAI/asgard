from http import HTTPStatus
from starlette.exceptions import HTTPException
from thor.web.transports.http_streaming import OdinHttpStreamingTransport
from thor.web.middleware.heimdall import HeimdallCurrentUserMiddleware
from thor.web.middleware.hermod import HermodStreamingMiddleware
from thor.config import settings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware import Middleware
from typing import List



async def handle_mcp_request(
    request: Request,
) -> Response:
    mcp_id = request.path_params.get("mcp_id")
    transport = OdinHttpStreamingTransport(
        mcp_id=mcp_id,
        user_info=request.state.user_info,
        organization_id=request.state.organization_id,
        channel_id=request.state.channel_id,
        supports_hermod_streaming=request.state.supports_hermod_streaming,
    )
    method = request.method.upper()
    if method == "GET":
        return await transport._handle_get() 
    elif method == "POST":
        body = await request.body()
        return await transport._handle_post(body) 
    elif method == "DELETE":
        return await transport._handle_delete() 
    else:
        raise HTTPException(status_code=HTTPStatus.METHOD_NOT_ALLOWED, detail="Method not allowed")
    

app = Starlette(
    debug=settings.DEBUG,
    middleware=[
        Middleware(BaseHTTPMiddleware, dispatch=HeimdallCurrentUserMiddleware()),
        Middleware(BaseHTTPMiddleware, dispatch=HermodStreamingMiddleware())
    ],
    routes=[
        Route( 
            "/{mcp_id}", 
            endpoint=handle_mcp_request, 
            methods=["GET", "POST", "DELETE"],
        ),
    ],
)
