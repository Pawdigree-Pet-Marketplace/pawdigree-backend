import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIRequestFactory

from accounts.serializers import (
    CustomerLoginSerializer,
    CustomerRegistrationSerializer,
    VendorLoginSerializer,
    VendorRegistrationSerializer,
)
from accounts.tests.test_email_case_handling import PASSWORD, registration_data
from accounts.views import PasswordResetRequestView

User = get_user_model()

CUSTOMER_PASSWORD = 'CustomerPass123!Secure'
VENDOR_PASSWORD = 'VendorPass123!Secure'


def build(serializer_class, email):
    data = registration_data(email)
    data.pop('username', None)
    return serializer_class(data=data)


def register(serializer_class, email):
    serializer = build(serializer_class, email)
    assert serializer.is_valid(), serializer.errors
    return serializer.save()


def make_pair(email='dual@example.com'):
    customer = User.objects.create_user(
        username='dualcustomer',
        email=email,
        password=CUSTOMER_PASSWORD,
        role=User.Role.CUSTOMER,
    )
    vendor = User.objects.create_user(
        username='dualvendor',
        email=email,
        password=VENDOR_PASSWORD,
        role=User.Role.VENDOR,
    )
    return customer, vendor


@pytest.mark.django_db
def test_same_email_can_register_as_customer_and_vendor():
    customer = register(CustomerRegistrationSerializer, 'dual@example.com')
    vendor = register(VendorRegistrationSerializer, 'Dual@Example.com')

    assert customer.pk != vendor.pk
    assert customer.role == User.Role.CUSTOMER
    assert vendor.role == User.Role.VENDOR
    assert customer.email == vendor.email == 'dual@example.com'
    assert User.objects.filter(email__iexact='dual@example.com').count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    'serializer_class',
    [CustomerRegistrationSerializer, VendorRegistrationSerializer],
)
def test_duplicate_email_in_same_role_is_rejected(serializer_class):
    register(serializer_class, 'same@example.com')

    serializer = build(serializer_class, 'SAME@example.com')

    assert not serializer.is_valid()
    assert 'email' in serializer.errors


@pytest.mark.django_db
def test_each_portal_logs_in_only_its_own_account():
    customer, vendor = make_pair()

    customer_login = CustomerLoginSerializer(
        data={'email': 'dual@example.com', 'password': CUSTOMER_PASSWORD}
    )
    assert customer_login.is_valid(), customer_login.errors
    assert customer_login.validated_data['user'].pk == customer.pk

    vendor_login = VendorLoginSerializer(
        data={'email': 'dual@example.com', 'password': VENDOR_PASSWORD}
    )
    assert vendor_login.is_valid(), vendor_login.errors
    assert vendor_login.validated_data['user'].pk == vendor.pk


@pytest.mark.django_db
def test_password_of_one_role_does_not_open_the_other_portal():
    make_pair()

    wrong_for_customer = CustomerLoginSerializer(
        data={'email': 'dual@example.com', 'password': VENDOR_PASSWORD}
    )
    wrong_for_vendor = VendorLoginSerializer(
        data={'email': 'dual@example.com', 'password': CUSTOMER_PASSWORD}
    )

    assert not wrong_for_customer.is_valid()
    assert not wrong_for_vendor.is_valid()


@pytest.mark.django_db
def test_password_reset_sends_a_link_for_each_account():
    customer, vendor = make_pair()

    request = APIRequestFactory().post(
        '/reset/', {'email': 'dual@example.com'}, format='json'
    )
    response = PasswordResetRequestView.as_view()(request)

    assert response.status_code == 200
    assert len(mail.outbox) == 2

    texts = []
    for message in mail.outbox:
        text = message.body
        for content, _mimetype in message.alternatives:
            text += content
        texts.append(text)

    for user in (customer, vendor):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        assert sum(f'uid={uid}' in text for text in texts) == 1
