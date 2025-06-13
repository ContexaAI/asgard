import base64
import json
from typing import Type
from starlette.exceptions import HTTPException


from thor.config import settings
from starlette.requests import Request


class HeimdallCurrentUserMiddleware:
    def __init__(self):
        pass
    
    async def __call__(self, request: Request, call_next):
        user_info_token = request.headers.get(settings.USER_INFO_TOKEN)

        if not user_info_token:
            raise HTTPException(status_code=401, detail='Unauthorized')

        try:
            # Decode the token from base64, then decode bytes to string, and load the JSON
            user_info_bytes = base64.b64decode(user_info_token)
            user_info_str = user_info_bytes.decode("utf-8")
            user_info = json.loads(user_info_str)
        except Exception as e:
            raise HTTPException(status_code=401, detail='Unauthorized')
            
        request.state.user_info = user_info
        organization_id = request.headers.get(settings.ORGANIZATION_HEADER, None)
        request.state.organization_id = organization_id

        response = await call_next(request)
        return response
    
