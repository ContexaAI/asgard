from datetime import datetime
from http import HTTPStatus
import json
from uuid import uuid4


from starlette.requests import Request
from starlette.responses import Response

from starlette.exceptions import HTTPException

from mcp.types import JSONRPCMessage, JSONRPCResponse, JSONRPCRequest, JSONRPCError, ErrorData, PARSE_ERROR, INVALID_REQUEST, INVALID_PARAMS, INTERNAL_ERROR, LoggingCapability, PromptsCapability, ResourcesCapability, ToolsCapability, JSONRPCNotification
from thor.config import settings
from thor.constants import (
    MCP_SESSION_ID_HEADER,
    LAST_EVENT_ID_HEADER,
    CONTENT_TYPE_HEADER,
    ACCEPT_HEADER,
    CONTENT_TYPE_JSON,
    CONTENT_TYPE_SSE,
    HERMOD_GRIP_HOLD_HEADER,
    HERMOD_GRIP_HOLD_MODE,
    HERMOD_GRIP_CHANNEL_HEADER,
    HERMOD_GRIP_KEEP_ALIVE_HEADER,
)
import jwt
from thor.worker import WorkerManager




class OdinHttpStreamingTransport:
    def __init__(
        self,
        request: Request,
        mcp_id: str,
    ):
        self.request = request
        self.supports_hermod_streaming = request.state.supports_hermod_streaming
        self.user_info = request.state.user_info
        self.channel_id = self.request.headers.get(MCP_SESSION_ID_HEADER, None)
        self.mcp_id = mcp_id
        self.worker = WorkerManager(
            mcp_id=self.mcp_id,
            organization_id=self.request.state.organization_id,
        )
    
    
        
    async def get_response(self) -> Response:
        
        method = self.request.method.upper()
        if method == "GET":
            return await self._handle_get() # -> Needs a validated session
        elif method == "POST":
            return await self._handle_post() # -> Needs a validated session. Doesnt need for initialize
        elif method == "DELETE":
            return await self._handle_delete() # -> Needs a validated session
        else:
            # For Method Not Allowed, a simple HTTP response is fine,
            # but if you want JSON-RPC, you could use _create_error_response
            raise HTTPException(status_code=HTTPStatus.METHOD_NOT_ALLOWED, detail="Method not allowed")
    
    
    async def _handle_get(self ) -> Response:
        
        if not self.supports_hermod_streaming:
            
            return self._create_error_response(
                error_message="Client must accept application/json or text/event-stream",
                status_code=HTTPStatus.NOT_ACCEPTABLE, # 406
                error_code=INVALID_REQUEST
            )
        if self.channel_id: 
            return self._create_streaming_hold_response(self.channel_id)
        else:
            return self._create_error_response(
                error_message="Session ID is required for GET.",
                status_code=HTTPStatus.BAD_REQUEST, # 400
                error_code=INVALID_REQUEST
            )
    
    async def _handle_delete(self) -> Response:
        if not self.channel_id:
            return self._create_error_response(
                error_message="Session ID is required for DELETE.",
                status_code=HTTPStatus.BAD_REQUEST, # 400
                error_code=INVALID_REQUEST
            )

        self.worker.terminate_session(
            channel_id=self.channel_id,
            user_info=self.user_info
        )
        return self._create_json_response(
            response_message=None,
            status_code=HTTPStatus.OK
        )
        
        

    async def _handle_post(self) -> Response:

        
        
        # 1: try to parse the request body as JSON. except and handle
        try:
            body = await self.request.body()
            if not body:

                return self._create_error_response(
                    error_message="Request body cannot be empty for POST.",
                    status_code=HTTPStatus.BAD_REQUEST, # 400
                    error_code=INVALID_REQUEST
                )
            json_data = json.loads(body)

        except json.JSONDecodeError as e:
            
            return self._create_error_response(
                error_message="Parse error: Invalid JSON was received by the server.",
                status_code=HTTPStatus.BAD_REQUEST, # 400
                error_code=PARSE_ERROR
            )

        # 2. should be JSONRPCMessage
        try:
            message = JSONRPCMessage.model_validate(json_data)
            
        except Exception as e:  
            return self._create_error_response(
                error_message="Invalid Request: The JSON sent is not a valid Request object.",
                status_code=HTTPStatus.BAD_REQUEST, # 400
                error_code=INVALID_REQUEST # Or INVALID_PARAMS if structure is okay but content is bad
            )

        # 3. check if initialize request
        if isinstance(message.root, JSONRPCRequest) and message.root.method == "initialize":
            
            response_message = self.worker.handle_initialize_request(
                request=message.root,
                channel_id=self.channel_id,
                user_info=self.user_info,
            )
            
            self.channel_id = self.create_new_user_channel(
                initialization_params=message.root.params
            )
            return self._create_json_response(
                response_message,
                status_code=HTTPStatus.OK,
            )
        
        if not self.channel_id:
            return self._create_error_response(
                error_message="Session ID is required for POST.",
                status_code=HTTPStatus.BAD_REQUEST, # 400
                error_code=INVALID_REQUEST
            )
        
            
        if isinstance(message.root, JSONRPCRequest):
            self.worker.handle_mcp_request(
                request=message.root, 
                channel_id=self.channel_id,
                user_info=self.user_info,
            )
            return self._create_json_response(
                response_message=None,
                status_code=HTTPStatus.ACCEPTED,
            )
        elif isinstance(message.root, JSONRPCNotification):
            self.worker.handle_mcp_notification(
                notification=message.root,
                channel_id=self.channel_id,
                user_info=self.user_info,
            )
            return self._create_json_response(
                response_message=None,
                status_code=HTTPStatus.ACCEPTED,
            )
        elif isinstance(message.root, JSONRPCResponse) or isinstance(message.root, JSONRPCError):
            self.worker.handle_mcp_response(
                response=message.root,
                channel_id=self.channel_id,
                user_info=self.user_info,
            )
            return self._create_json_response(
                response_message=message.root,
                status_code=HTTPStatus.ACCEPTED,
            )
        else:
            return self._create_error_response(
                error_message="Invalid Request: The JSON sent is not a valid Request object.",
                status_code=HTTPStatus.BAD_REQUEST, # 400
                error_code=INVALID_REQUEST # Or INVALID_PARAMS if structure is okay but content is bad
            )
    
    
    def _create_error_response(
        self,
        error_message: str,
        status_code: HTTPStatus,
        error_code: int = INVALID_REQUEST,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Create a JSON-RPC error response."""
        response_headers = {
            CONTENT_TYPE_HEADER: CONTENT_TYPE_JSON,
            MCP_SESSION_ID_HEADER: self.channel_id,
        }
        if headers:
            response_headers.update(headers)

        error_data = ErrorData(code=error_code, message=error_message)
        json_rpc_error = JSONRPCError(
            jsonrpc="2.0",
            id=None,  # JSON-RPC errors can have a null id
            error=error_data,
        )

        return Response(
            json_rpc_error.model_dump_json(by_alias=True, exclude_none=True),
            status_code=status_code,
            headers=response_headers,
        )
    
    def _create_json_response(
        self,
        response_message: JSONRPCMessage | None,
        status_code: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Create a JSON response from a JSONRPCMessage"""
        response_headers = {
            CONTENT_TYPE_HEADER: CONTENT_TYPE_JSON,
            MCP_SESSION_ID_HEADER: self.channel_id,
        }
        if headers:
            response_headers.update(headers)
        return Response(
            response_message.model_dump_json(by_alias=True, exclude_none=True)
            if response_message
            else None,
            status_code=status_code,
            headers=response_headers,
        )
        
    def _create_streaming_hold_response(
        self,
        channel_id,
        status_code: HTTPStatus = HTTPStatus.ACCEPTED,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Create a streaming hold response"""
        response_headers = {
            CONTENT_TYPE_HEADER: CONTENT_TYPE_SSE, 
            HERMOD_GRIP_HOLD_HEADER: HERMOD_GRIP_HOLD_MODE,
            HERMOD_GRIP_CHANNEL_HEADER: channel_id,
            HERMOD_GRIP_KEEP_ALIVE_HEADER: f"\\n; format=cstring; timeout={settings.HERMOD_STREAMING_KEEP_ALIVE_TIMEOUT}",
            MCP_SESSION_ID_HEADER: channel_id,
            ACCEPT_HEADER: CONTENT_TYPE_JSON,
        }
        
        if headers:
            response_headers.update(headers)

        return Response(
            content=None,
            status_code=status_code,
            headers=response_headers,
        )

    def create_new_user_channel(
        self,
        initialization_params: dict
    ) -> str:
        """Create a new user channel"""
        payload = {
            "user_info": self.request.state.user_info,
            "client_params": initialization_params,
            "created_at": datetime.now().isoformat(),
            "organization_id": self.request.state.organization_id,
            "mcp_id": self.mcp_id,
        }
        return jwt.encode(payload, settings.HERMOD_STREAMING_TOKEN_SECRET, algorithm="HS256")