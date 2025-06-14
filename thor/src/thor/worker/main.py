import hashlib
from http import HTTPStatus
from typing import Optional, Union
from celery.result import AsyncResult
from mcp.types import (
    CancelledNotification, ProgressNotification, ClientNotification
)
from celery import Celery, states
from starlette.exceptions import HTTPException
from thor.constants import MCP_CELERY_PROGRESS_STATE
from thor.config import settings
from mcp.types import JSONRPCRequest, JSONRPCNotification, JSONRPCResponse, JSONRPCError, ErrorData, JSONRPCMessage, ServerResult
from mcp.shared.session import (
    SendRequestT, SendResultT, SendNotificationT, ReceiveResultT, ProgressFnT, RequestId
)
from mcp.shared.session import SessionMessage
import json
import zmq
import time
from asgiref.sync import async_to_sync




class WorkerManager:

    def __init__(
        self, 
        mcp_id: str,
        organization_id: Optional[str] = None,
    ):
        self.worker = self._build_worker()
        self.mcp_id = mcp_id
        self.organization_id = organization_id

    def get_worker(self):
        return self.worker

    def get_queue_name(self):
        if self.organization_id:
            return f"{self.organization_id}_{self.mcp_id}"
        return self.mcp_id


    def send_task(self, 
        task_name: str, 
        args: tuple, 
    ):
        queue = self.get_queue_name()
        return self.worker.send_task(
            task_name, 
            args=args,
            queue=queue
        )

    def handle_initialize_request(self, 
        request: JSONRPCRequest, 
        channel_id: str, 
        user_info: dict, 
    ):
        task = self.send_task(
            "handle_mcp_request", 
            args=(request.model_dump_json(by_alias=True, exclude_none=True), channel_id, user_info),
        )
        task = AsyncResult(str(task))
        res = task.get()
        return JSONRPCResponse.model_validate_json(res)
    
    def handle_mcp_request(
        self, 
        request: JSONRPCRequest,
        channel_id: str, 
        user_info: dict, 
    ):

        self.send_task(
            "handle_mcp_request", 
            args=(request.model_dump_json(by_alias=True, exclude_none=True), channel_id, user_info),
        )
    
    def handle_mcp_notification(
        self, 
        notification: JSONRPCNotification, 
        channel_id: str, 
        user_info: dict, 
    ):
        self.send_task(
            "handle_mcp_notification", 
            args=(notification.model_dump_json(by_alias=True, exclude_none=True), channel_id, user_info),
        )
    
    def handle_mcp_response(
        self, 
        response: Union[JSONRPCResponse, JSONRPCError], 
        channel_id: str, 
        user_info: dict, 
    ):
        self.send_task(
            "handle_mcp_response", 
            args=(response.model_dump_json(by_alias=True, exclude_none=True), channel_id, user_info),
            task_id=self._generate_response_task_id(response.id, channel_id),
        )

    def terminate_session(self, channel_id: str, user_info: dict):
        self.send_task(
            "terminate_session", 
            args=(channel_id, user_info)
        )

    def _build_worker(self):
        worker =  Celery(
            broker=settings.CELERY_BROKER,
            backend=settings.CELERY_BACKEND
        )
        worker.task(self.task_handle_mcp_request, name="handle_mcp_request")
        worker.task(self.task_handle_mcp_notification, name="handle_mcp_notification")
        worker.task(self.task_handle_mcp_response, name="handle_mcp_response")
        worker.task(self.task_terminate_session, name="terminate_session")
        return worker

    def _generate_response_task_id(self, request_id: str, channel_id: str) -> str:
        return f"response_{channel_id}_{request_id}"

    def _get_hermod_socket(self) -> zmq.Socket:
        zmq_context = zmq.Context()
        hermod_socket = zmq_context.socket(zmq.PUB)
        for url in settings.HERMOD_STREAMING_ZERO_MQ_URLS:
            hermod_socket.connect(url)
        # TODO: wait till socket is ready instead of time.sleep
        time.sleep(0.1)
        return hermod_socket

    def _send_sse_message(
        self, 
        message: SessionMessage,
        channel_id: str,
    ) -> None:
        hermod_socket = self._get_hermod_socket()
        content = "event: message\ndata: " + message.message.model_dump_json(by_alias=True, exclude_none=True)
        item = {
            "channel": channel_id,
            "formats":{
                "http-stream": {
                    "content": content +"\n\n"
                }
            }
        }
        hermod_socket.send_multipart(
            [
                channel_id.encode(),
                ("J" + json.dumps(item)).encode(),
            ]
        )

    async def _send_response(
        self,
        response: SendResultT | ErrorData,
        request_id: RequestId,
        channel_id: str,
    ) -> None:
        if isinstance(response, ErrorData):
            jsonrpc_error = JSONRPCError(jsonrpc="2.0", id=request_id, error=response)
            message = JSONRPCMessage(jsonrpc_error)
        else:
            jsonrpc_response = JSONRPCResponse(
                jsonrpc="2.0",
                id=request_id,
                result=response.model_dump(
                    by_alias=True, mode="json", exclude_none=True
                ),
            )
            message = JSONRPCMessage(jsonrpc_response)
        session_message = SessionMessage(message=message)
        self._send_sse_message(session_message, channel_id)

    def _send_zmq_message(self, message: str):
        """Helper method to send a message over ZMQ with optional response handling.
        
        Args:
            message: The message to send
            
        Returns:
            Response from ZMQ server if expect_response is True, or ErrorData on error, or None if no response expected
        """
        zmq_url = settings.ODINMCP_ZMQ_URL
        
        # Initialize variables
        context = None
        socket = None
        reply_message = None
        
        try:
            context = zmq.Context()
            socket = context.socket(zmq.REQ)
            
            # Set timeouts to prevent indefinite blocking
            socket.setsockopt(zmq.LINGER, 0)  # Discard pending messages on close immediately
            socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 seconds timeout for receive
            socket.setsockopt(zmq.SNDTIMEO, 5000)  # 5 seconds timeout for send
            
            socket.connect(zmq_url)
            socket.send_string(message)
            
            # Only wait for reply if expected
            
            reply_message = socket.recv_string()
            return reply_message
                
        except zmq.error.ZMQError as e:
            return ErrorData(code=0, message=str(e), data=None)
            
        except Exception as e:
            return ErrorData(code=0, message=str(e), data=None)
            
        finally:
            if socket is not None:
                socket.close()
            if context is not None:
                context.term()
    
    def task_handle_mcp_request(self, request: str, channel_id: str, user_info: dict) -> None:
        
        rpc_request = JSONRPCRequest.model_validate_json(request)

        reply = self._send_zmq_message(request)


        if not reply:
            return ErrorData(code=0, message="No reply received", data=None)

        if not isinstance(reply, ErrorData):
            found_model = False
            # Use a more efficient approach with a single try block
            for model_class in [ServerResult, ErrorData]:
                try:
                    reply = model_class.model_validate_json(reply)
                    found_model = True
                    break  # Stop if validation succeeds
                except Exception:
                    continue  # Try next model class
            
            if not found_model:
                reply = ErrorData(code=0, message=f"Failed to parse response as valid model", data=None)

        response = JSONRPCResponse(
            jsonrpc="2.0",
            id=rpc_request.id,
            result=reply.model_dump(
                by_alias=True, mode="json", exclude_none=True
            ),
        )

        if rpc_request.method != "initialize":
            self._send_response(
                response=response,
                request_id=rpc_request.id,
                channel_id=channel_id,
            )
        return response.model_dump_json(by_alias=True, exclude_none=True)
        

    def task_handle_mcp_notification(self, notification: str, channel_id: str, user_info: str) -> None:
        cli_notif = ClientNotification(json.loads(notification))
        
        user_info = json.loads(user_info)

        if isinstance(cli_notif.root, CancelledNotification):
            cancelled_id = cli_notif.root.params.requestId
            task_id = self._generate_response_task_id(cancelled_id, channel_id)
            task = AsyncResult(task_id)
            
            if not (task.successful() or task.failed()):
                self.worker.control.revoke(task_id)
            

        elif isinstance(cli_notif.root, ProgressNotification):
            progress_id = cli_notif.root.params.progressToken
            task_id = self._generate_response_task_id(progress_id, channel_id)
            task = AsyncResult(task_id)
            if not (task.successful() or task.failed() or task.state  == states.REVOKED):
                task.backend.store_result(
                    task_id,
                    result=cli_notif.root.model_dump_json(by_alias=True, exclude_none=True),
                    state=MCP_CELERY_PROGRESS_STATE,
                )

        # Send notification over ZMQ, ignoring response
        return self._send_zmq_message(notification)
        
    def task_handle_mcp_response(self, response: str, channel_id: str, user_info: str) -> None:
        return response
    
    def task_terminate_session(self, channel_id: str, user_info: str) -> None:
        
        hermod_socket = self._get_hermod_socket()
        item = {
            "channel": channel_id,
            "formats":{
                "http-stream": {
                    "action":"close",
                }
            }
        }
        hermod_socket.send_multipart(
            [
                channel_id.encode(),
                ("J" + json.dumps(item)).encode(),
            ]
        )