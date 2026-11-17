from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.token_utils import SessionRefreshToken
from audit.models import AuditLog

User = get_user_model()


def make_user(username, role, **extra):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='SecurePass123!',
        role=role,
        **extra,
    )


class AdminUserLifecycleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.system_admin = make_user('lifecycle_sysadmin', User.Role.SYSTEM_ADMIN)
        self.customer = make_user('lifecycle_customer', User.Role.CUSTOMER)
        self.vendor = make_user(
            'lifecycle_vendor',
            User.Role.VENDOR,
            is_active=False,
            status=User.AccountStatus.DEACTIVATED,
        )
        self.client.force_authenticate(user=self.system_admin)

    def action_url(self, user, action):
        return reverse(f'admin-user-{action}', args=[user.pk])

    def test_system_admin_activates_a_deactivated_vendor(self):
        response = self.client.post(self.action_url(self.vendor, 'activate'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.vendor.pk)
        self.assertEqual(response.data['status'], 'active')
        self.vendor.refresh_from_db()
        self.assertTrue(self.vendor.is_active)
        event = AuditLog.objects.get(action='user.activated')
        self.assertEqual(event.actor, self.system_admin)
        self.assertEqual(event.target_id, str(self.vendor.pk))
        self.assertEqual(
            event.details,
            {'from_status': 'deactivated', 'to_status': 'active'},
        )

    def test_system_admin_deactivates_customer_and_revokes_refresh_token(self):
        refresh = SessionRefreshToken.for_user(self.customer)

        response = self.client.post(self.action_url(self.customer, 'deactivate'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'deactivated')
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        event = AuditLog.objects.get(action='user.deactivated')
        self.assertEqual(event.actor, self.system_admin)
        self.assertEqual(event.target_id, str(self.customer.pk))

        refresh_response = APIClient().post(
            reverse('token-refresh'), {'refresh': str(refresh)}, format='json'
        )
        self.assertEqual(
            refresh_response.status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_repeating_a_deactivation_does_not_duplicate_audit_event(self):
        url = self.action_url(self.customer, 'deactivate')

        first = self.client.post(url)
        second = self.client.post(url)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(
            AuditLog.objects.filter(
                action='user.deactivated', target_id=str(self.customer.pk)
            ).count(),
            1,
        )

    def test_suspension_requires_a_non_empty_trimmed_reason(self):
        url = reverse('admin-user-suspend', args=[self.customer.pk])
        for reason in (None, '   '):
            response = self.client.post(
                url,
                {} if reason is None else {'reason': reason},
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(
            url,
            {'reason': '  Repeated policy violations  '},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'suspended')
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertEqual(self.customer.status, User.AccountStatus.SUSPENDED)
        event = AuditLog.objects.get(action='user.suspended')
        self.assertEqual(event.target_id, str(self.customer.pk))
        self.assertEqual(
            event.details,
            {
                'from_status': 'active',
                'to_status': 'suspended',
                'reason': 'Repeated policy violations',
            },
        )

    def test_reactivation_preserves_suspension_audit_history(self):
        suspend_url = reverse('admin-user-suspend', args=[self.customer.pk])
        activate_url = self.action_url(self.customer, 'activate')
        self.client.post(
            suspend_url, {'reason': 'Keep this history'}, format='json'
        )
        suspension = AuditLog.objects.get(action='user.suspended')

        response = self.client.post(activate_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, User.AccountStatus.ACTIVE)
        self.assertTrue(self.customer.is_active)
        suspension.refresh_from_db()
        self.assertEqual(
            suspension.details['reason'], 'Keep this history'
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action='user.activated', target_id=str(self.customer.pk)
            ).exists()
        )

    def test_suspension_revokes_refresh_tokens(self):
        refresh = SessionRefreshToken.for_user(self.customer)
        response = self.client.post(
            reverse('admin-user-suspend', args=[self.customer.pk]),
            {'reason': 'Policy violation'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refreshed = APIClient().post(
            reverse('token-refresh'), {'refresh': str(refresh)}, format='json'
        )
        self.assertEqual(refreshed.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_only_system_admins_can_use_user_lifecycle_endpoints(self):
        url = self.action_url(self.customer, 'deactivate')
        for role in (User.Role.ADMIN, User.Role.VENDOR, User.Role.CUSTOMER):
            user = make_user(f'lifecycle_denied_{role.lower()}', role)
            self.client.force_authenticate(user=user)
            response = self.client.post(url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=None)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
