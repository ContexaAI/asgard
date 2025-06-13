import logging
from starlette.exceptions import HTTPException
from starlette.requests import Request
from thor.config import settings
from thor.constants import (
    MCP_SESSION_ID_HEADER,
    LAST_EVENT_ID_HEADER,
    CONTENT_TYPE_HEADER,
    ACCEPT_HEADER,
    CONTENT_TYPE_JSON,
    CONTENT_TYPE_SSE,
)
from http import HTTPStatus
import jwt


class HermodStreamingMiddleware:

    def validate_hermod_streaming_token(self, token:str, request:Request) -> bool:
        try:
            payload = jwt.decode(token, settings.HERMOD_STREAMING_TOKEN_SECRET, algorithms=["HS256"])
            if payload.get("organization_id") != request.state.organization_id:
                return False
            
            if payload.get("user_info") != request.state.user_info:
                return False
            
            if payload.get("mcp_id") != request.path_params.get("mcp_id"):
                return False

            return True
        except Exception as e:
            return False

    async def __call__(self, request: Request, call_next):
        # existing hermod bypass
        supports_hermod_streaming = (request.headers.get(settings.HERMOD_STREAMING_HEADER, "false") == "true")
        
        accept_hdr = request.headers.get(ACCEPT_HEADER, "")
        
        if not supports_hermod_streaming and CONTENT_TYPE_SSE in accept_hdr:
            request.headers[ACCEPT_HEADER] = accept_hdr.replace(CONTENT_TYPE_SSE, "")
            supports_hermod_streaming = False
        elif supports_hermod_streaming and CONTENT_TYPE_JSON in accept_hdr:
            supports_hermod_streaming = True
            
        
        request.supports_hermod_streaming = supports_hermod_streaming
        
        # 1. if mcp-session-id exists -> it should be valid   
        channel_id = request.headers.get(MCP_SESSION_ID_HEADER, None)
        
        if channel_id and not self.validate_hermod_streaming_token(channel_id, request):
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="User not found",
                headers={MCP_SESSION_ID_HEADER: channel_id}
            )
        
        
        # 2. Not Acceptable
        if CONTENT_TYPE_JSON not in accept_hdr and CONTENT_TYPE_SSE not in accept_hdr:
            raise HTTPException(
                status_code=HTTPStatus.NOT_ACCEPTABLE,
                detail=f"Client must accept {CONTENT_TYPE_JSON} or {CONTENT_TYPE_SSE}",
                headers={MCP_SESSION_ID_HEADER: channel_id} if channel_id else {}
            )
        
        return await call_next(request)
