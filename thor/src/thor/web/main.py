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
    mcp_id: str,
) -> Response:
    transport = OdinHttpStreamingTransport(request, mcp_id)
    return await transport.get_response()

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
