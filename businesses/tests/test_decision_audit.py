from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from businesses.models import Business

Status = Business.VerificationStatus

REASON = "The trading licence photo is unreadable."


class BusinessDecisionAuditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="audit_admin",
            email="audit-admin@example.com",
            password="Test12345!",
            role=User.Role.ADMIN,
        )
        self.vendor = User.objects.create_user(
            username="audit_vendor",
            email="audit-vendor@example.com",
            password="Test12345!",
            role=User.Role.VENDOR,
        )
        self.business = Business.objects.create(
            vendor=self.vendor,
            name="Audit Paws",
            description="Pets",
            contact="0700000000",
            email="audit-paws@example.com",
            address="1 Main St",
            city_district="Kampala",
            verification_status=Status.PENDING,
        )
        self.client = APIClient()

    def set_status(self, value):
        Business.objects.filter(pk=self.business.pk).update(
            verification_status=value
        )

    def decide(self, user, body):
        self.client.force_authenticate(user)
        url = reverse("business-admin-decision", kwargs={"pk": self.business.pk})
        return self.client.post(url, body, format="json")

    def test_approval_is_recorded(self):
        response = self.decide(self.admin, {"action": "approve"})

        self.assertEqual(response.status_code, 200)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "business.decided")
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.actor_role, self.admin.role)
        self.assertEqual(entry.target_type, "businesses.business")
        self.assertEqual(entry.target_id, str(self.business.pk))
        self.assertEqual(
            entry.details,
            {
                "decision": "approve",
                "from_status": Status.PENDING.value,
                "to_status": Status.APPROVED.value,
            },
        )

    def test_requested_changes_are_recorded_without_the_reason(self):
        response = self.decide(
            self.admin, {"action": "request_changes", "reason": REASON}
        )

        self.assertEqual(response.status_code, 200)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.details["decision"], "request_changes")
        self.assertEqual(
            entry.details["to_status"], Status.CHANGES_REQUESTED.value
        )
        self.assertNotIn(REASON, str(entry.details))

    def test_suspend_then_reapprove_are_both_recorded(self):
        self.set_status(Status.APPROVED)

        self.decide(self.admin, {"action": "suspend", "reason": REASON})
        self.decide(self.admin, {"action": "reapprove"})

        decisions = list(
            AuditLog.objects.order_by("created_at").values_list(
                "details__decision", flat=True
            )
        )
        self.assertEqual(decisions, ["suspend", "reapprove"])

    def test_a_decision_from_the_wrong_status_is_not_recorded(self):
        self.set_status(Status.APPROVED)

        response = self.decide(self.admin, {"action": "approve"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_a_missing_reason_is_not_recorded(self):
        response = self.decide(self.admin, {"action": "request_changes"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_a_vendor_cannot_decide_and_nothing_is_recorded(self):
        response = self.decide(self.vendor, {"action": "approve"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(AuditLog.objects.count(), 0)
