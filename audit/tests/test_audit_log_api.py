from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditLog
from audit.services import record

URL = reverse('audit-log-list')


@pytest.fixture
def entries(admin, vendor):
    first = record(actor=admin, action='pet.updated', target=vendor)
    second = record(actor=vendor, action='product.created')
    return first, second


@pytest.mark.django_db
def test_requires_login(api_client):
    assert api_client.get(URL).status_code == 401


@pytest.mark.django_db
def test_customer_is_forbidden(api_client, customer, entries):
    api_client.force_authenticate(customer)
    assert api_client.get(URL).status_code == 403


@pytest.mark.django_db
def test_vendor_is_forbidden(api_client, vendor, entries):
    api_client.force_authenticate(vendor)
    assert api_client.get(URL).status_code == 403


@pytest.mark.django_db
def test_admin_and_system_admin_can_list(
    api_client, admin, system_admin, entries
):
    for user in (admin, system_admin):
        api_client.force_authenticate(user)
        response = api_client.get(URL)
        assert response.status_code == 200
        assert response.data['count'] == 2


@pytest.mark.django_db
def test_newest_first_and_fields(api_client, admin, entries):
    api_client.force_authenticate(admin)
    results = api_client.get(URL).data['results']

    assert results[0]['action'] == 'product.created'
    assert set(results[0]) == {
        'id',
        'actor',
        'actor_email',
        'actor_role',
        'action',
        'target_type',
        'target_id',
        'target_label',
        'details',
        'created_at',
    }


@pytest.mark.django_db
def test_filter_by_user_id_and_email(api_client, admin, vendor, entries):
    api_client.force_authenticate(admin)

    by_id = api_client.get(URL, {'user': vendor.pk}).data['results']
    assert [r['action'] for r in by_id] == ['product.created']

    by_email = api_client.get(URL, {'user': 'admin@'}).data['results']
    assert [r['action'] for r in by_email] == ['pet.updated']


@pytest.mark.django_db
def test_filter_by_action(api_client, admin, entries):
    api_client.force_authenticate(admin)

    one = api_client.get(URL, {'action': 'pet.updated'}).data['results']
    assert [r['action'] for r in one] == ['pet.updated']

    both = api_client.get(
        URL, {'action': 'pet.updated,product.created'}
    ).data['results']
    assert len(both) == 2


@pytest.mark.django_db
def test_filter_by_date(api_client, admin, entries):
    old = entries[0]
    AuditLog.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )
    api_client.force_authenticate(admin)

    today = timezone.now().date().isoformat()
    recent = api_client.get(URL, {'date_from': today}).data['results']
    assert [r['action'] for r in recent] == ['product.created']

    cutoff = (timezone.now() - timedelta(days=5)).date().isoformat()
    older = api_client.get(URL, {'date_to': cutoff}).data['results']
    assert [r['action'] for r in older] == ['pet.updated']


@pytest.mark.django_db
def test_bad_date_is_a_400(api_client, admin):
    api_client.force_authenticate(admin)
    response = api_client.get(URL, {'date_from': 'tomorrow'})

    assert response.status_code == 400
    assert 'date_from' in response.data


@pytest.mark.django_db
def test_endpoint_is_read_only(api_client, admin):
    api_client.force_authenticate(admin)
    assert api_client.post(URL, {}, format='json').status_code == 405
