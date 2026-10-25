import asyncio
import httpx
from fastapi.testclient import TestClient
import main,mobile_gateway
from test_production_flow import client


def test_gateway_keeps_all_cookie_headers_and_closes_stream():
    closed = []

    class Content(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'complete-response'

        async def aclose(self):
            closed.append(True)

    def handle(request):
        return httpx.Response(200, headers=[('Set-Cookie', 'one=1; Path=/'),
                                          ('Set-Cookie', 'two=2; Path=/')], stream=Content())

    backend = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    mobile_gateway.app.state.backend = backend
    proxy = TestClient(mobile_gateway.app)
    try:
        response = proxy.get('/cookies')
        assert response.content == b'complete-response'
        assert len(response.headers.get_list('set-cookie')) == 2
        assert proxy.cookies.get('one') == '1' and proxy.cookies.get('two') == '2'
        assert closed
    finally:
        proxy.close()
        asyncio.run(backend.aclose())

def test_gateway_never_shares_admin_or_station_cookies_between_browsers(client):
    backend=httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://127.0.0.1:8000')
    mobile_gateway.app.state.backend=backend
    first=TestClient(mobile_gateway.app)
    second=TestClient(mobile_gateway.app)
    try:
        login=first.post('/api/auth/login',json={'username':'fixtureadmin','password':'TestOnly-Password-739'})
        assert login.status_code==200
        assert first.get('/api/flow/admin').status_code==200
        # The shared upstream transport has received Set-Cookie; the next
        # browser must still be unauthenticated rather than inheriting admin.
        assert second.get('/api/flow/admin').status_code==401
        guest=first.get('/api/worker/session').json()
        assert second.get('/api/flow/admin').status_code==401
        other=second.get('/api/worker/session').json()
        assert guest['id']!=other['id']
        assert first.get('/api/worker/session').json()['id']==guest['id']
        assert second.get('/api/worker/session').json()['id']==other['id']
    finally:
        first.close();second.close();asyncio.run(backend.aclose())
