import os
os.environ['IVY_DISABLE_LLM'] = '1'
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
resp = client.post('/chat/query', json={'question': 'Bonjour'})
print(resp.status_code)
print(resp.text)
