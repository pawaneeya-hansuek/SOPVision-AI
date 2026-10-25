"""Real setup/login for isolated test databases; no production auth bypass."""
import auth
def bootstrap(client):
    response=client.post('/api/auth/setup',json={'username':'fixtureadmin','display_name':'Fixture Admin','password':'TestOnly-Password-739','code':auth.setup_path().read_text().strip()})
    assert response.status_code==200,response.text
    me=client.get('/api/auth/me')
    assert me.status_code==200,me.text
    client.headers['X-CSRF-Token']=me.json()['csrf_token']
    return client
