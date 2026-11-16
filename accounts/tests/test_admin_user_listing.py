from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


def make_user(username, role, **extra):
    email = extra.pop('email', f'{username}@example.com')
    return User.objects.create_user(
        username=username,
        email=email,
        password='SecurePass123!',
        role=role,
        **extra,
    )


class AdminUserListingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.system_admin = make_user('listing_sysadmin', User.Role.SYSTEM_ADMIN)
        self.url = reverse('admin-user-list')

    def list_as_system_admin(self, **params):
        self.client.force_authenticate(user=self.system_admin)
        return self.client.get(self.url, params)

    def test_system_admin_lists_eligible_roles_without_sensitive_fields(self):
        customer = make_user(
            'listing_customer', User.Role.CUSTOMER, first_name='Casey'
        )
        vendor = make_user('listing_vendor', User.Role.VENDOR)
        admin = make_user('listing_admin', User.Role.ADMIN, is_staff=True)
        make_user('hidden_sysadmin', User.Role.SYSTEM_ADMIN)
        make_user(
            'hidden_superuser',
            User.Role.VENDOR,
            is_staff=True,
            is_superuser=True,
        )

        response = self.list_as_system_admin()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(
            {row['id'] for row in response.data['results']},
            {customer.pk, vendor.pk, admin.pk},
        )
        row = next(
            row for row in response.data['results'] if row['id'] == customer.pk
        )
        self.assertEqual(
            set(row),
            {
                'id',
                'first_name',
                'last_name',
                'email',
                'role',
                'status',
                'date_joined',
            },
        )
        self.assertEqual(row['status'], 'active')
        self.assertNotIn('password', row)
        self.assertNotIn('is_staff', row)
        self.assertNotIn('is_superuser', row)

    def test_regular_admin_vendor_customer_and_anonymous_are_denied(self):
        for user in (
            make_user('listing_regular_admin', User.Role.ADMIN),
            make_user('listing_vendor_denied', User.Role.VENDOR),
            make_user('listing_customer_denied', User.Role.CUSTOMER),
        ):
            with self.subTest(role=user.role):
                self.client.force_authenticate(user=user)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_search_matches_username_names_and_email(self):
        matches = [
            make_user('needle_username', User.Role.CUSTOMER),
            make_user('first_match', User.Role.VENDOR, first_name='Needle'),
            make_user('last_match', User.Role.ADMIN, last_name='Needle'),
            make_user('email_match', User.Role.CUSTOMER, email='needle@example.com'),
        ]
        make_user('not_a_match', User.Role.CUSTOMER)

        response = self.list_as_system_admin(search='needle')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {row['id'] for row in response.data['results']},
            {user.pk for user in matches},
        )

    def test_role_and_status_filters_can_be_combined(self):
        target = make_user('filter_target', User.Role.VENDOR, is_active=False)
        make_user('filter_active_vendor', User.Role.VENDOR)
        make_user('filter_inactive_customer', User.Role.CUSTOMER, is_active=False)

        response = self.list_as_system_admin(role='VENDOR', status='deactivated')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row['id'] for row in response.data['results']], [target.pk]
        )
        self.assertEqual(response.data['results'][0]['status'], 'deactivated')

    def test_invalid_role_and_status_filters_return_400(self):
        self.assertEqual(
            self.list_as_system_admin(role='SYSTEM_ADMIN').status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.list_as_system_admin(status='suspended').status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_pagination_and_summary_cover_the_entire_eligible_population(self):
        make_user('summary_active_customer', User.Role.CUSTOMER)
        make_user('summary_inactive_vendor', User.Role.VENDOR, is_active=False)
        make_user('summary_admin', User.Role.ADMIN, is_staff=True)
        make_user('summary_hidden_sysadmin', User.Role.SYSTEM_ADMIN)
        make_user(
            'summary_hidden_superuser',
            User.Role.VENDOR,
            is_staff=True,
            is_superuser=True,
        )

        response = self.list_as_system_admin(
            role='CUSTOMER', page=1, page_size=1
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(
            response.data['summary'],
            {
                'total': 3,
                'active': 2,
                'deactivated': 1,
                'suspended': 0,
            },
        )
        self.assertIsNone(response.data['next'])
        self.assertIsNone(response.data['previous'])

    def test_page_size_is_capped(self):
        User.objects.bulk_create([
            User(
                username=f'page_size_user_{index}',
                email=f'page_size_user_{index}@example.com',
                role=User.Role.CUSTOMER,
            )
            for index in range(55)
        ])

        response = self.list_as_system_admin(page_size=500)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 50)
        self.assertIsNotNone(response.data['next'])
