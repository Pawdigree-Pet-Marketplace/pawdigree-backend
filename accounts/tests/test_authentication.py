import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User


@pytest.mark.django_db
def test_customer_can_register():
    client = APIClient()

    payload = {
        'username': 'newcustomer',
        'first_name': 'Test',
        'last_name': 'Customer',
        'email': 'newcustomer@example.com',
        'phone': '0700000000',
        'password': 'SecurePass123',
    }

    response = client.post(
        reverse('customer-register'),
        payload,
        format='json',
    )

    assert response.status_code == status.HTTP_201_CREATED

    user = User.objects.get(email=payload['email'])

    assert user.role == User.Role.CUSTOMER
    assert user.check_password(payload['password'])


@pytest.mark.django_db
def test_customer_cannot_register_with_duplicate_email():
    client = APIClient()

    User.objects.create_user(
        username='existingcustomer',
        email='existing@example.com',
        password='SecurePass123',
        role=User.Role.CUSTOMER,
    )

    payload = {
        'username': 'anothercustomer',
        'first_name': 'Another',
        'last_name': 'Customer',
        'email': 'existing@example.com',
        'phone': '0700000001',
        'password': 'SecurePass123',
    }

    response = client.post(
        reverse('customer-register'),
        payload,
        format='json',
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'email' in response.data

@pytest.mark.django_db
def test_vendor_can_register():
    client = APIClient()

    payload = {
        'username': 'newvendor',
        'first_name': 'Test',
        'last_name': 'Vendor',
        'email': 'newvendor@example.com',
        'phone': '0700000002',
        'password': 'SecurePass123',
    }

    response = client.post(
        reverse('vendor-register'),
        payload,
        format='json',
    )

    assert response.status_code == status.HTTP_201_CREATED

    user = User.objects.get(email=payload['email'])

    assert user.role == User.Role.VENDOR
    assert user.check_password(payload['password'])


@pytest.mark.django_db
def test_vendor_cannot_register_with_duplicate_email():
    client = APIClient()

    User.objects.create_user(
        username='existingvendor',
        email='existingvendor@example.com',
        password='SecurePass123',
        role=User.Role.VENDOR,
    )

    payload = {
        'username': 'anothervendor',
        'first_name': 'Another',
        'last_name': 'Vendor',
        'email': 'existingvendor@example.com',
        'phone': '0700000003',
        'password': 'SecurePass123',
    }

    response = client.post(
        reverse('vendor-register'),
        payload,
        format='json',
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'email' in response.data

@pytest.fixture
def customer():
    password = 'SecurePass123'

    user = User.objects.create_user(
        username='logincustomer',
        email='logincustomer@example.com',
        password=password,
        role=User.Role.CUSTOMER,
    )

    return user, password


@pytest.mark.django_db
def test_customer_can_login(customer):
    user, password = customer
    client = APIClient()

    payload = {
        'email': user.email,
        'password': password,
    }

    response = client.post(
        reverse('customer-login'),
        payload,
        format='json',
    )

    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data
    assert 'refresh' in response.data


@pytest.mark.django_db
def test_customer_cannot_login_with_wrong_password(customer):
    user, _ = customer
    client = APIClient()

    payload = {
        'email': user.email,
        'password': 'WrongPassword123',
    }

    response = client.post(
        reverse('customer-login'),
        payload,
        format='json',
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'non_field_errors' in response.data


@pytest.mark.django_db
def test_vendor_cannot_use_customer_login():
    client = APIClient()

    vendor = User.objects.create_user(
        username='loginvendor',
        email='loginvendor@example.com',
        password='SecurePass123',
        role=User.Role.VENDOR,
    )

    payload = {
        'email': vendor.email,
        'password': 'SecurePass123',
    }

    response = client.post(
        reverse('customer-login'),
        payload,
        format='json',
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'non_field_errors' in response.data


@pytest.fixture
def vendor():
    password = 'SecurePass123'

    user = User.objects.create_user(
        username='loginvendor',
        email='loginvendor@example.com',
        password=password,
        role=User.Role.VENDOR,
    )

    return user, password


@pytest.mark.django_db
def test_vendor_can_login(vendor):
    user, password = vendor
    client = APIClient()

    payload = {
        'email': user.email,
        'password': password,
    }

    response = client.post(
        reverse('vendor-login'),
        payload,
        format='json',
    )

    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data
    assert 'refresh' in response.data


@pytest.mark.django_db
def test_vendor_cannot_login_with_wrong_password(vendor):
    user, _ = vendor
    client = APIClient()

    payload = {
        'email': user.email,
        'password': 'WrongPassword123',
    }

    response = client.post(
        reverse('vendor-login'),
        payload,
        format='json',
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'non_field_errors' in response.data


@pytest.mark.django_db
def test_customer_cannot_use_vendor_login():
    client = APIClient()

    customer = User.objects.create_user(
        username='customervendorlogin',
        email='customervendorlogin@example.com',
        password='SecurePass123',
        role=User.Role.CUSTOMER,
    )

    payload = {
        'email': customer.email,
        'password': 'SecurePass123',
    }

    response = client.post(
        reverse('vendor-login'),
        payload,
        format='json',
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'non_field_errors' in response.data


@pytest.fixture
def logout_user():
    user = User.objects.create_user(
        username='logoutuser',
        email='logoutuser@example.com',
        password='SecurePass123',
        role=User.Role.CUSTOMER,
    )

    refresh_token = RefreshToken.for_user(user)

    return user, refresh_token


@pytest.mark.django_db
def test_anonymous_user_cannot_logout(logout_user):
    _, refresh_token = logout_user
    client = APIClient()

    response = client.post(
        reverse('logout'),
        {'refresh': str(refresh_token)},
        format='json',
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_authenticated_user_can_logout_with_valid_refresh_token(logout_user):
    user, refresh_token = logout_user
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        reverse('logout'),
        {'refresh': str(refresh_token)},
        format='json',
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data['detail'] == 'Successfully logged out.'


@pytest.mark.django_db
def test_blacklisted_refresh_token_cannot_be_used_again(logout_user):
    user, refresh_token = logout_user
    client = APIClient()
    client.force_authenticate(user=user)

    refresh_token = str(refresh_token)

    client.post(
        reverse('logout'),
        {'refresh': refresh_token},
        format='json',
    )

    response = client.post(
        reverse('logout'),
        {'refresh': refresh_token},
        format='json',
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_anonymous_user_cannot_access_profile():
    client = APIClient()

    get_response = client.get(reverse('customer-profile'))
    patch_response = client.patch(
        reverse('customer-profile'),
        {'first_name': 'Blocked'},
        format='json',
    )

    assert get_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert patch_response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_customer_can_get_and_patch_own_profile(customer):
    user, _ = customer
    client = APIClient()
    client.force_authenticate(user=user)

    get_response = client.get(reverse('customer-profile'))
    patch_response = client.patch(
        reverse('customer-profile'),
        {'first_name': 'Updated'},
        format='json',
    )

    assert get_response.status_code == status.HTTP_200_OK
    assert get_response.data['email'] == user.email
    assert patch_response.status_code == status.HTTP_200_OK

    user.refresh_from_db()
    assert user.first_name == 'Updated'


@pytest.mark.django_db
def test_non_customer_users_cannot_access_customer_profile():
    customer = User.objects.create_user(
        username='profilecustomer',
        email='profilecustomer@example.com',
        password='SecurePass123',
        role=User.Role.CUSTOMER,
    )
    vendor = User.objects.create_user(
        username='profilevendor',
        email='profilevendor@example.com',
        password='SecurePass123',
        role=User.Role.VENDOR,
    )
    admin = User.objects.create_user(
        username='profileadmin',
        email='profileadmin@example.com',
        password='SecurePass123',
        role=User.Role.ADMIN,
    )
    system_admin = User.objects.create_user(
        username='profilesystemadmin',
        email='profilesystemadmin@example.com',
        password='SecurePass123',
        role=User.Role.SYSTEM_ADMIN,
    )

    for user in (customer, vendor, admin, system_admin):
        client = APIClient()
        client.force_authenticate(user=user)
        get_response = client.get(reverse('customer-profile'))
        patch_response = client.patch(
            reverse('customer-profile'),
            {'first_name': 'Blocked'},
            format='json',
        )

        if user == customer:
            assert get_response.status_code == status.HTTP_200_OK
            assert patch_response.status_code == status.HTTP_200_OK
        else:
            assert get_response.status_code == status.HTTP_403_FORBIDDEN
            assert patch_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_anonymous_user_cannot_access_current_user():
    client = APIClient()

    response = client.get(reverse('current-user'))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.parametrize(
    'role',
    [
        User.Role.CUSTOMER,
        User.Role.VENDOR,
        User.Role.ADMIN,
        User.Role.SYSTEM_ADMIN,
    ],
)
def test_authenticated_users_can_get_current_user(role):
    user = User.objects.create_user(
        username=f'currentuser_{role}',
        email=f'currentuser_{role}@example.com',
        password='SecurePass123',
        role=role,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(reverse('current-user'))

    assert response.status_code == status.HTTP_200_OK
    assert response.data['id'] == user.id
    assert response.data['username'] == user.username
    assert response.data['email'] == user.email
    assert response.data['role'] == user.role
    assert response.data['isActive'] is user.is_active
    assert response.data['accountStatus'] == (
        'active' if user.is_active else 'inactive'
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    'is_active, expected_status',
    [
        (True, 'active'),
        (False, 'inactive'),
    ],
)
def test_current_user_reports_account_status(is_active, expected_status):
    user = User.objects.create_user(
        username=f'currentuser_status_{is_active}',
        email=f'currentuser_status_{is_active}@example.com',
        password='SecurePass123',
        role=User.Role.CUSTOMER,
        is_active=is_active,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(reverse('current-user'))

    assert response.status_code == status.HTTP_200_OK
    assert response.data['isActive'] is is_active
    assert response.data['accountStatus'] == expected_status