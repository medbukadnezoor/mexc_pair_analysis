import os
import sys
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import app

client = TestClient(app)

def test_pairs():
    resp = client.get('/pairs')
    assert resp.status_code == 200
    data = resp.json()
    assert 'symbols' in data
    assert isinstance(data['symbols'], list)
    assert len(data['symbols']) > 0

def test_analyze_invalid():
    resp = client.post('/analyze', json={'base': 'NOTAPAIR'})
    assert resp.status_code == 400

def test_analyze_valid():
    # This may fail if BTCUSDT is not available or API is down, but should not 500
    resp = client.post('/analyze', json={'base': 'BTCUSDT'})
    assert resp.status_code in (200, 502, 400)


def test_export_csv():
    resp = client.get('/export/csv')
    assert resp.status_code == 200
    assert resp.headers['content-type'].startswith('text/csv')
