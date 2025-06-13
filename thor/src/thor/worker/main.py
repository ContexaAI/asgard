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
from mcp.types import JSONRPCRequest, JSONRPCNotification, JSONRPCResponse, JSONRPCError

import json
import zmq
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
        self.worker.send_task(
            task_name, 
            args=args,
            queue=queue
        )

    def  handle_initialize_request(self, 
        request: JSONRPCRequest, 
        channel_id: str, 
        user_info: dict, 
    ):
        self.send_task(
            "handle_initialize_request", 
            args=(request.model_dump_json(by_alias=True, exclude_none=True), channel_id, user_info),
        )
    
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
        worker.task(self.task_handle_initialize_request, name="handle_initialize_request")
        worker.task(self.task_handle_mcp_request, name="handle_mcp_request")
        worker.task(self.task_handle_mcp_notification, name="handle_mcp_notification")
        worker.task(self.task_handle_mcp_response, name="handle_mcp_response")
        worker.task(self.task_terminate_session, name="terminate_session")
        return worker

    def _generate_response_task_id(self, request_id: str, channel_id: str) -> str:
        return f"response_{channel_id}_{request_id}"

    def task_handle_mcp_request(self, request: str, channel_id: str, user_info: dict) -> None:
        return async_to_sync(self.task_async_handle_mcp_request)(request, channel_id, user_info)

    async def task_async_handle_mcp_request(self, request: str, channel_id: str, user_info: dict) -> None:
        # TODO: do something here
        print("handle_mcp_request")
        pass

    def task_handle_initialize_request(self, request: str, channel_id: str, user_info: dict) -> None:
        # TODO: do something here
        print(f"handle_initialize_request received for channel {channel_id} with user_info: {user_info}")
        print(f"Original request content (first 200 chars): {request[:200]}")

        context = None
        socket = None
        try:
            context = zmq.Context()
            socket = context.socket(zmq.REQ)
            # Set timeouts to prevent indefinite blocking
            socket.setsockopt(zmq.LINGER, 0)  # Discard pending messages on close immediately
            socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 seconds timeout for receive
            socket.setsockopt(zmq.SNDTIMEO, 5000)  # 5 seconds timeout for send

            socket.connect("tcp://localhost:5555")

            print(f"Sending ZMQ request (first 200 chars): {request[:200]}...")
            socket.send_string(request)

            # Wait for the reply
            reply_message = socket.recv_string()
            print(f"Received ZMQ reply (first 200 chars): {reply_message[:200]}...")

        except zmq.error.ZMQError as e:
            print(f"ZMQ Error in task_handle_initialize_request: {e}")
            # Depending on requirements, you might want to raise an exception,
            # send an error response, or handle it in another way.
        except Exception as e:
            print(f"An unexpected error occurred in task_handle_initialize_request: {e}")
        finally:
            if socket is not None:
                socket.close()
            if context is not None:
                context.term()

    def task_handle_mcp_notification(self, notification: str, channel_id: str, user_info: str) -> None:
        return async_to_sync(self.task_async_handle_mcp_notification)(notification, channel_id, user_info)
    
    async def task_async_handle_mcp_notification(self, notification: str, channel_id: str, user_info: str) -> None:
        cli_notif = ClientNotification(json.loads(notification))
        
        user_info = json.loads(user_info)

        if isinstance(cli_notif.root, CancelledNotification):
            cancelled_id = cli_notif.root.params.requestId
            task_id = self._generate_response_task_id(cancelled_id, channel_id)
            task = AsyncResult(task_id)
            
            if not (task.successful() or task.failed()):
                self.worker.control.revoke(task_id)
            

        if isinstance(cli_notif.root, ProgressNotification):
            progress_id = cli_notif.root.params.progressToken
            task_id = self._generate_response_task_id(progress_id, channel_id)
            task = AsyncResult(task_id)
            if not (task.successful() or task.failed() or task.state  == states.REVOKED):
                task.backend.store_result(
                    task_id,
                    result=cli_notif.root.model_dump_json(by_alias=True, exclude_none=True),
                    state=MCP_CELERY_PROGRESS_STATE,
                )

        # TODO: do something here
        print("handle_mcp_notification")
        
    def task_handle_mcp_response(self, response: str, channel_id: str, user_info: str) -> None:
        return async_to_sync(self.task_async_handle_mcp_response)(response, channel_id, user_info)
    
    async def task_async_handle_mcp_response(self, response: str, channel_id: str, user_info: str) -> str:
        return response
    
    def task_terminate_session(self, channel_id: str, user_info: str) -> None:
        user_info = json.loads(user_info)
        # TODO: do something here
        print("handle_terminate_session")
        
        
        