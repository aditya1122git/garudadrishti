import os
os.environ['SEED_MOCK_DATA'] = 'true'
os.environ['DEMO_IN_MEMORY'] = 'true'
os.environ['SCHEDULER_ENABLED'] = 'false'
import csv
import io
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope='module')
def client():
    with TestClient(app) as client:
        yield client

@pytest.fixture(scope='module')
def auth(client):
    response = client.post('/api/auth/token', data={'username': 'admin@jannetra.local', 'password': 'JanNetra-Demo-2026!'})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_auth_required(client):
    assert client.get('/api/overview').status_code == 401


def test_overview_math_and_demo_isolation(client, auth):
    data = client.get('/api/overview', headers=auth).json()
    totals = data['today']
    assert data['demo'] is True
    assert data['classifier']['provider'] == 'Hugging Face sentiment + Gemini target verifier'
    assert data['classifier']['status'] == 'demo'
    assert data['classifier']['model'] == 'cardiffnlp/twitter-xlm-roberta-base-sentiment'
    assert totals['total_count'] == 1650
    assert sum(totals[k + '_count'] for k in ['positive', 'negative', 'neutral', 'mixed']) == totals['total_count']
    assert abs(totals['negativity_index'] - totals['negative_count'] / 1650 * 100) < .1
    assert len(data['trend']) == 30
    assert {p['platform'] for p in data['platform_totals']} == {'x', 'youtube'}
    assert client.get('/api/overview?platform=facebook', headers=auth).json()['today'] is None
    assert client.get('/api/posts?platform=facebook', headers=auth).json()['total'] == 0


def test_search_filter_sort(client, auth):
    response = client.get('/api/posts?q=जन&sentiment=negative&sort=engagement', headers=auth)
    assert response.status_code == 200
    items = response.json()['items']
    assert all(p['sentiment']['label'] == 'negative' and 'जन' in p['content'] for p in items)
    scores = [p['engagement_score'] for p in items]
    assert scores == sorted(scores, reverse=True)


def test_exports(client, auth):
    csv_response = client.get('/api/export?period=weekly&format=csv', headers=auth)
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode('utf-8-sig'))))
    assert len(rows) == 14 and all(r['mode'] == 'DEMO' for r in rows)
    pdf = client.get('/api/export?period=monthly&format=pdf', headers=auth)
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')


def test_viewer_cannot_mutate(client, auth):
    value = {'email': 'viewer@example.org', 'password': 'Viewer-Long-Password!', 'role': 'viewer'}
    assert client.post('/api/users', headers=auth, json=value).status_code == 201
    login = client.post('/api/auth/token', data={'username': value['email'], 'password': value['password']}).json()
    viewer = {'Authorization': 'Bearer ' + login['access_token']}
    assert client.get('/api/overview', headers=viewer).status_code == 200
    assert client.post('/api/sync', headers=viewer).status_code == 403
    assert client.put('/api/settings', headers=viewer, json={'threshold': 10, 'keywords': ['PK']}).status_code == 403


def test_no_secret_import_or_demo_credential_storage(client, auth):
    response = client.put('/api/credentials', headers=auth, json={'platform': 'youtube', 'api_key': 'secret-real-credential'})
    assert response.status_code == 409
    assert 'encrypted_api_key' not in client.get('/api/settings', headers=auth).text
    assert client.post('/api/import', headers=auth).status_code == 404


def test_admin_can_update_automation_window(client, auth):
    before = client.get('/api/settings', headers=auth).json()
    keywords = [row['keyword'] for row in before['keywords'] if row['is_active']]
    response = client.put('/api/settings', headers=auth, json={
        'keywords': keywords,
        'automation_start_hour': 7,
        'automation_end_hour': 21,
    })
    assert response.status_code == 200
    after = client.get('/api/settings', headers=auth).json()
    assert after['automation_start_hour'] == 7
    assert after['automation_end_hour'] == 21
    invalid = client.put('/api/settings', headers=auth, json={
        'keywords': keywords,
        'automation_start_hour': 21,
        'automation_end_hour': 7,
    })
    assert invalid.status_code == 422


def test_user_can_update_profile_email_name_and_password(client, auth):
    original = {'email': 'profile-user@example.org', 'password': 'Profile-Old-Password!', 'role': 'viewer'}
    assert client.post('/api/users', headers=auth, json=original).status_code == 201
    login = client.post('/api/auth/token', data={'username': original['email'], 'password': original['password']})
    token = {'Authorization': 'Bearer ' + login.json()['access_token']}
    updated = {
        'name': 'Campaign Analyst', 'email': 'analyst-profile@example.org',
        'current_password': original['password'], 'new_password': 'NewPass9!',
    }
    response = client.put('/api/profile', headers=token, json=updated)
    assert response.status_code == 200
    assert response.json()['name'] == 'Campaign Analyst'
    assert client.get('/api/profile', headers=token).json()['email'] == updated['email']
    assert client.post('/api/auth/token', data={'username': original['email'], 'password': original['password']}).status_code == 401
    assert client.post('/api/auth/token', data={'username': updated['email'], 'password': updated['new_password']}).status_code == 200


def test_profile_password_requires_8_to_14_characters(client, auth):
    profile = client.get('/api/profile', headers=auth).json()
    for invalid in ('Short7', 'Password-Way-Too-Long'):
        response = client.put('/api/profile', headers=auth, json={
            'name': profile['name'], 'email': profile['email'],
            'current_password': 'JanNetra-Demo-2026!', 'new_password': invalid,
        })
        assert response.status_code == 422
