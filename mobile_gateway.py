"""HTTPS entry point forwarding to the single local production backend.

Do not initialize the production database here: opening the mobile entry point
must never mark an ongoing desktop session as interrupted.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import anyio
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, StreamingResponse

BACKEND = 'http://127.0.0.1:8000'
ROOT = Path(__file__).resolve().parent
HOP_HEADERS = {'host', 'connection', 'keep-alive', 'proxy-authenticate',
               'proxy-authorization', 'te', 'trailer', 'transfer-encoding', 'upgrade'}


def forwarded_headers(headers):
    excluded = HOP_HEADERS | {v.strip().lower() for v in headers.get('connection', '').split(',')}
    return [(k, v) for k, v in headers.multi_items() if k.lower() not in excluded]


@asynccontextmanager
async def lifespan(app):
    owned = None
    async with httpx.AsyncClient(base_url=BACKEND, trust_env=False, timeout=30) as client:
        try:
            await client.get('/api/health', timeout=2)
        except httpx.ConnectError:
            owned = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000', '--timeout-graceful-shutdown', '5', '--no-access-log',
                cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            ready = False
            for _ in range(40):
                try:
                    response = await client.get('/api/health', timeout=2)
                    if response.status_code == 200 and response.json().get('ok'):
                        ready = True
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                await asyncio.sleep(.25)
            if not ready:
                raise RuntimeError('Production backend on port 8000 is unavailable or outdated. Restart start_windows.bat.')
            app.state.backend = client
            yield
        finally:
            if owned and owned.returncode is None:
                owned.terminate()
                await owned.wait()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.api_route('/{path:path}', methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
async def forward(request: Request, path: str):
    # Construct the upstream URL from a fixed origin, never a client-supplied host.
    raw_path = request.scope['raw_path']
    if request.scope['query_string']:
        raw_path += b'?' + request.scope['query_string']
    url = httpx.URL(BACKEND).copy_with(raw_path=raw_path)
    headers = httpx.Headers(request.headers.raw)
    headers['x-forwarded-proto'] = request.url.scheme
    # AsyncClient has a shared cookie jar. Always supply the caller's Cookie
    # header explicitly so another browser's upstream session is never reused.
    headers['cookie'] = request.headers.get('cookie', '')
    upstream = request.app.state.backend.build_request(
        request.method, url, headers=forwarded_headers(headers), content=request.stream())
    try:
        response = await request.app.state.backend.send(upstream, stream=True)
    except httpx.HTTPError:
        return JSONResponse({'detail': 'ขาดการเชื่อมต่อเซิร์ฟเวอร์หลัก กรุณาตรวจสถานะก่อนสแกนชิ้นถัดไป'}, status_code=502)
    async def content():
        try:
            async for part in response.aiter_raw():
                yield part
        finally:
            with anyio.CancelScope(shield=True):
                await response.aclose()

    try:
        result = StreamingResponse(content(), status_code=response.status_code)
        # A mapping collapses repeated Set-Cookie headers (login/session updates).
        result.raw_headers = [(k.encode('latin-1'), v.encode('latin-1'))
                              for k, v in forwarded_headers(response.headers)]
        return result
    except BaseException:
        await response.aclose()
        raise
