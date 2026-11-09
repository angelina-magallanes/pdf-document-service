import asyncio
from time import monotonic

from starlette.exceptions import HTTPException
from starlette.requests import Request

from app import settings
from app.errors import problem_response


class LimitedReceive:
    def __init__(self, receive):
        self.receive = receive
        self.total = 0
        self.deadline = monotonic() + settings.body_timeout_seconds

    async def __call__(self):
        try:
            async with asyncio.timeout(max(0, self.deadline - monotonic())):
                message = await self.receive()
        except TimeoutError:
            raise HTTPException(408, "Tiempo de recepción del cuerpo agotado") from None
        self.total += len(message.get("body", b""))
        if self.total > settings.max_body_bytes:
            raise HTTPException(413, "El cuerpo HTTP excede el tamaño permitido")
        return message


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        lengths = request.headers.getlist("content-length")
        if lengths and (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()):
            response = problem_response(request, 400, "Content-Length inválido")
            return await response(scope, receive, send)
        if lengths and (len(lengths[0]) > 20 or int(lengths[0]) > settings.max_body_bytes):
            response = problem_response(request, 413, "El cuerpo HTTP excede el tamaño permitido")
            return await response(scope, receive, send)
        await self.app(scope, LimitedReceive(receive), send)
