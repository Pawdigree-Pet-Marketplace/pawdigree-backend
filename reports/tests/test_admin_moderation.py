from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from bookings.tests.helpers import make_service
from cart.tests.helpers import make_business, make_category, make_product, make_user
from notification.models import Notification
from pets.models import Pet
from products.models import Product
from reports.models import Report
from reviews.models import Review, ReviewReply

LISTING_KINDS = ("PET", "PRODUCT", "SERVICE")


class ModerationTestCase(TestCase):
    def setUp(self):
        self.admin = make_user("modadmin", User.Role.ADMIN)
        self.vendor = make_user("modvendor", User.Role.VENDOR)
        self.customer = make_user("modcustomer", User.Role.CUSTOMER)
        self.other_customer = make_user("modcustomer2", User.Role.CUSTOMER)
        self.business = make_business(self.vendor, name="Mod Business")
        self.category = make_category()
        self.pet = Pet.objects.create(
            vendor=self.vendor,
            business=self.business,
            listing_type="ADOPTION",
            name="Rex",
            age=12,
            gender=Pet.Gender.UNKNOWN,
            size=Pet.Size.MEDIUM,
            approved=True,
        )
        self.product = make_product(
            self.business, self.category, name="Toy", price="10.00", stock=5
        )
        Product.objects.filter(pk=self.product.pk).update(approved=True)
        self.product.refresh_from_db()
        self.service = make_service(self.business, name="Grooming")

        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def items(self):
        return {"PET": self.pet, "PRODUCT": self.product, "SERVICE": self.service}

    def make_report(self, kind, item_id=None, reporter=None):
        return Report.objects.create(
            reporter=reporter or self.customer,
            reason=Report.Reason.INAPPROPRIATE_CONTENT,
            description="Looks wrong",
            reported_item_type=kind,
            reported_item_id=None if item_id is None else str(item_id),
        )

    def make_review(self):
        return Review.objects.create(
            customer=self.customer, product=self.product, rating=1, comment="Awful"
        )

    def url(self, name, pk=None):
        return reverse(name, args=[pk] if pk is not None else [])

    def remove(self, report, reason="Breaks the rules"):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                self.url("report-admin-remove", report.pk),
                {"reason": reason},
                format="json",
            )

    def dismiss(self, report, status="DISMISSED", note=""):
        return self.client.patch(
            self.url("report-admin-status", report.pk),
            {"status": status, "note": note},
            format="json",
        )

    def audit(self, action):
        return AuditLog.objects.filter(action=action)


class AccessTests(ModerationTestCase):
    def test_anonymous_is_rejected(self):
        report = self.make_report("PET", self.pet.pk)
        client = APIClient()
        self.assertEqual(client.get(self.url("report-admin-list")).status_code, 401)
        self.assertEqual(
            client.get(self.url("report-admin-detail", report.pk)).status_code, 401
        )

    def test_customers_and_vendors_are_rejected(self):
        report = self.make_report("PET", self.pet.pk)
        for user in (self.customer, self.vendor):
            with self.subTest(role=user.role):
                client = APIClient()
                client.force_authenticate(user)
                self.assertEqual(client.get(self.url("report-admin-list")).status_code, 403)
                self.assertEqual(
                    client.get(self.url("report-admin-detail", report.pk)).status_code, 403
                )
                self.assertEqual(
                    client.patch(
                        self.url("report-admin-status", report.pk),
                        {"status": "DISMISSED"},
                        format="json",
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    client.post(
                        self.url("report-admin-remove", report.pk),
                        {"reason": "x"},
                        format="json",
                    ).status_code,
                    403,
                )
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.PENDING)
        self.pet.refresh_from_db()
        self.assertTrue(self.pet.approved)


class QueueTests(ModerationTestCase):
    def test_default_is_pending_oldest_first(self):
        first = self.make_report("PET", self.pet.pk)
        second = self.make_report("PRODUCT", self.product.pk)
        handled = self.make_report("SERVICE", self.service.pk)
        self.dismiss(handled)

        data = self.client.get(self.url("report-admin-list")).json()
        self.assertEqual(data["count"], 2)
        self.assertEqual([row["id"] for row in data["results"]], [first.pk, second.pk])

    def test_status_and_type_filters(self):
        pet_report = self.make_report("PET", self.pet.pk)
        self.make_report("PRODUCT", self.product.pk)
        self.dismiss(pet_report)

        dismissed = self.client.get(self.url("report-admin-list"), {"status": "DISMISSED"})
        self.assertEqual([row["id"] for row in dismissed.json()["results"]], [pet_report.pk])
        products = self.client.get(
            self.url("report-admin-list"), {"reported_item_type": "PRODUCT"}
        )
        self.assertEqual(products.json()["count"], 1)

    def test_invalid_filters_are_rejected(self):
        self.assertEqual(
            self.client.get(self.url("report-admin-list"), {"status": "bogus"}).status_code, 400
        )
        self.assertEqual(
            self.client.get(
                self.url("report-admin-list"), {"reported_item_type": "bogus"}
            ).status_code,
            400,
        )

    def test_pagination(self):
        for _ in range(3):
            self.make_report("PET", self.pet.pk)
        data = self.client.get(self.url("report-admin-list"), {"page_size": 2}).json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["results"]), 2)
        self.assertIsNotNone(data["next"])

    def test_row_shows_the_item_and_no_reporter_email(self):
        report = self.make_report("PET", self.pet.pk)
        row = self.client.get(self.url("report-admin-detail", report.pk)).json()

        self.assertEqual(row["status"], "PENDING")
        self.assertEqual(row["reporter"]["id"], self.customer.pk)
        self.assertNotIn("email", row["reporter"])
        self.assertEqual(row["item"]["name"], "Rex")
        self.assertEqual(row["item"]["business_name"], "Mod Business")
        self.assertFalse(row["item"]["removed"])
        self.assertIsNone(row["reviewed_by"])

    def test_review_and_general_and_deleted_items(self):
        review = self.make_review()
        review_report = self.make_report("REVIEW", review.pk)
        general = self.make_report("GENERAL")
        gone = self.make_report("PET", self.pet.pk)
        self.pet.delete()

        review_row = self.client.get(self.url("report-admin-detail", review_report.pk)).json()
        self.assertEqual(review_row["item"]["comment"], "Awful")
        general_row = self.client.get(self.url("report-admin-detail", general.pk)).json()
        self.assertIsNone(general_row["item"])
        gone_row = self.client.get(self.url("report-admin-detail", gone.pk)).json()
        self.assertEqual(gone_row["item"], {"exists": False})

    def test_unknown_report_is_404(self):
        self.assertEqual(self.client.get(self.url("report-admin-detail", 999999)).status_code, 404)


class DismissTests(ModerationTestCase):
    def test_dismiss_records_who_when_and_audit(self):
        report = self.make_report("PET", self.pet.pk)
        response = self.dismiss(report, note="Not a problem")

        self.assertEqual(response.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.DISMISSED)
        self.assertEqual(report.reviewed_by, self.admin)
        self.assertIsNotNone(report.reviewed_at)
        self.assertEqual(report.resolution_note, "Not a problem")
        self.assertEqual(response.json()["reviewed_by"]["id"], self.admin.pk)
        self.assertEqual(self.audit("report.dismissed").count(), 1)
        self.pet.refresh_from_db()
        self.assertTrue(self.pet.approved)

    def test_a_handled_report_cannot_be_changed_again(self):
        report = self.make_report("PET", self.pet.pk)
        self.assertEqual(self.dismiss(report).status_code, 200)
        self.assertEqual(self.dismiss(report).status_code, 400)
        self.assertEqual(self.remove(report).status_code, 400)
        self.assertEqual(self.audit("report.dismissed").count(), 1)

    def test_resolved_is_only_for_general_reports(self):
        item_report = self.make_report("PET", self.pet.pk)
        general = self.make_report("GENERAL")
        self.assertEqual(self.dismiss(item_report, status="RESOLVED").status_code, 400)
        self.assertEqual(self.dismiss(general, status="RESOLVED").status_code, 200)
        item_report.refresh_from_db()
        general.refresh_from_db()
        self.assertEqual(item_report.status, Report.Status.PENDING)
        self.assertEqual(general.status, Report.Status.RESOLVED)
        self.assertEqual(self.audit("report.resolved").count(), 1)

    def test_invalid_status_and_unknown_report(self):
        report = self.make_report("PET", self.pet.pk)
        self.assertEqual(self.dismiss(report, status="PENDING").status_code, 400)
        self.assertEqual(self.dismiss(report, status="bogus").status_code, 400)
        missing = self.client.patch(
            self.url("report-admin-status", 999999), {"status": "DISMISSED"}, format="json"
        )
        self.assertEqual(missing.status_code, 404)

    def test_dismissing_works_when_the_item_is_gone(self):
        report = self.make_report("PET", self.pet.pk)
        self.pet.delete()
        self.assertEqual(self.dismiss(report).status_code, 200)


class RemoveTests(ModerationTestCase):
    def test_removing_a_listing_rejects_it_and_tells_the_vendor(self):
        rejections = 0
        for kind in LISTING_KINDS:
            with self.subTest(kind=kind):
                item = self.items()[kind]
                report = self.make_report(kind, item.pk)
                response = self.remove(report, reason="Misleading photos")

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "RESOLVED")
                item.refresh_from_db()
                self.assertFalse(item.approved)
                self.assertEqual(item.rejection_reason, "Misleading photos")
                self.assertEqual(item.reviewed_by_id, self.admin.pk)
                report.refresh_from_db()
                self.assertEqual(report.status, Report.Status.RESOLVED)
                self.assertEqual(report.reviewed_by, self.admin)
                self.assertEqual(report.resolution_note, "Misleading photos")
                self.assertEqual(self.audit(f"{kind.lower()}.rejected").count(), 1)
                rejections += 1
                self.assertEqual(
                    Notification.objects.filter(
                        user=self.vendor, type=Notification.Type.LISTING_REJECTED
                    ).count(),
                    rejections,
                )
        self.assertEqual(self.audit("report.resolved").count(), 3)

    def test_removing_a_review_hides_it_and_keeps_its_replies(self):
        review = self.make_review()
        ReviewReply.objects.create(review=review, author=self.vendor, body="So sorry")
        report = self.make_report("REVIEW", review.pk)

        response = self.remove(report)
        self.assertEqual(response.status_code, 200)
        review.refresh_from_db()
        self.assertFalse(review.is_visible)
        self.assertEqual(review.replies.count(), 1)
        self.assertEqual(self.audit("review.hidden").count(), 1)
        self.assertEqual(self.audit("report.resolved").count(), 1)

    def test_a_reason_is_required_and_nothing_changes_without_it(self):
        report = self.make_report("PET", self.pet.pk)
        for body in ({}, {"reason": ""}, {"reason": "   "}):
            with self.subTest(body=body):
                response = self.client.post(
                    self.url("report-admin-remove", report.pk), body, format="json"
                )
                self.assertEqual(response.status_code, 400)
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.PENDING)
        self.pet.refresh_from_db()
        self.assertTrue(self.pet.approved)
        self.assertEqual(self.audit("pet.rejected").count(), 0)

    def test_a_general_report_has_nothing_to_remove(self):
        report = self.make_report("GENERAL")
        self.assertEqual(self.remove(report).status_code, 400)
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.PENDING)

    def test_a_missing_item_cannot_be_removed(self):
        report = self.make_report("PET", self.pet.pk)
        self.pet.delete()
        self.assertEqual(self.remove(report).status_code, 400)
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.PENDING)

    def test_unknown_report_is_404(self):
        response = self.client.post(
            self.url("report-admin-remove", 999999), {"reason": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_other_pending_reports_on_the_same_item_are_resolved_together(self):
        first = self.make_report("PET", self.pet.pk)
        second = self.make_report("PET", self.pet.pk, reporter=self.other_customer)
        unrelated = self.make_report("PRODUCT", self.product.pk)

        self.assertEqual(self.remove(first).status_code, 200)
        for report in (first, second, unrelated):
            report.refresh_from_db()
        self.assertEqual(first.status, Report.Status.RESOLVED)
        self.assertEqual(second.status, Report.Status.RESOLVED)
        self.assertEqual(second.reviewed_by, self.admin)
        self.assertEqual(unrelated.status, Report.Status.PENDING)
        entry = self.audit("report.resolved").get()
        self.assertEqual(entry.details["also_resolved"], [second.pk])
        self.assertEqual(self.audit("pet.rejected").count(), 1)

    def test_an_already_removed_listing_still_resolves_the_report(self):
        Pet.objects.filter(pk=self.pet.pk).update(
            approved=False, rejection_reason="Earlier reason"
        )
        report = self.make_report("PET", self.pet.pk)

        self.assertEqual(self.remove(report, reason="Second reason").status_code, 200)
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.rejection_reason, "Earlier reason")
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.RESOLVED)
        self.assertEqual(self.audit("pet.rejected").count(), 0)
        self.assertEqual(self.audit("report.resolved").get().details["outcome"], "already_removed")
        self.assertEqual(
            Notification.objects.filter(
                user=self.vendor, type=Notification.Type.LISTING_REJECTED
            ).count(),
            0,
        )

    def test_an_already_hidden_review_still_resolves_the_report(self):
        review = self.make_review()
        Review.objects.filter(pk=review.pk).update(is_visible=False)
        report = self.make_report("REVIEW", review.pk)

        self.assertEqual(self.remove(report).status_code, 200)
        self.assertEqual(self.audit("review.hidden").count(), 0)
        self.assertEqual(self.audit("report.resolved").get().details["outcome"], "already_removed")


class ReviewReportSubmissionTests(ModerationTestCase):
    def submit(self, item_id):
        client = APIClient()
        client.force_authenticate(self.other_customer)
        return client.post(
            reverse("report-create"),
            {
                "reason": "OFFENSIVE_CONTENT",
                "description": "This review contains abusive language about the seller.",
                "reported_item_type": "REVIEW",
                "reported_item_id": str(item_id),
            },
            format="json",
        )

    def test_a_review_can_be_reported(self):
        review = self.make_review()
        response = self.submit(review.pk)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["reported_item_type"], "REVIEW")
        self.assertEqual(Report.objects.filter(reported_item_type="REVIEW").count(), 1)

    def test_a_missing_review_is_refused(self):
        self.assertEqual(self.submit(999999).status_code, 400)
