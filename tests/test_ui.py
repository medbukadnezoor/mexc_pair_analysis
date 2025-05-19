import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_autocomplete_appears():
    resp = client.get('/pairs')
    assert resp.status_code == 200
    data = resp.json()
    assert 'symbols' in data
    assert len(data['symbols']) > 0

# UI/SPA tests for autocomplete and table rendering would be done with a headless browser in cloud CI
# Here we just check backend endpoints are ready for frontend
