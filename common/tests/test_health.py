def test_health_returns_ok_without_login(api_client):
    # No django_db mark: pytest-django blocks database access in this
    # test, so it also proves the endpoint never queries the database.
    response = api_client.get('/api/health/')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_health_ignores_a_bad_token(api_client):
    api_client.credentials(HTTP_AUTHORIZATION='Bearer not-a-real-token')

    response = api_client.get('/api/health/')

    assert response.status_code == 200