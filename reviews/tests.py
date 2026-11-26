"""Tests for the reviews app.

Run with:  python manage.py test reviews
"""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from adoptions.models import AdoptionApplication
from bookings.models import Booking
from cart.models import Cart, CartItem
from cart.tests.helpers import make_business, make_category, make_product, make_user
from orders.models import VendorOrder
from orders.services import change_status, checkout, mark_paid
from orders.tests.test_pet_checkout import PAYLOAD, make_pet
from pets.models import Pet
from products.models import Product
from services.models import Service

from .models import Review
from .models import ReviewReply
from .serializers import (
    MAX_COMMENT_CHARS,
    MAX_COMMENT_WORDS,
    ReviewCreateSerializer,
    ReviewReplySerializer,
    ReviewUpdateSerializer,
    count_words,
)
from .services import (
    check_eligibility,
    create_reply,
    create_review,
    rating_summary,
    resolve_target,
    with_ratings,
)

STATUS = VendorOrder.Status
STEPS = (STATUS.PROCESSING, STATUS.SHIPPED, STATUS.DELIVERED)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def buy(customer, vendor, *, product=None, pet=None, until=STATUS.DELIVERED):
    """Put one item in the cart, check out, pay, and move it along.

    `until` is the last status to reach: "PENDING" (checked out, unpaid),
    PAID, PROCESSING, SHIPPED, DELIVERED or CANCELLED (a paid order the
    vendor cancelled). Returns the order for "PENDING", else the vendor order.
    """
    cart, _ = Cart.objects.get_or_create(customer=customer)
    CartItem.objects.create(cart=cart, product=product, pet=pet, quantity=1)
    order = checkout(customer, PAYLOAD)
    if until == "PENDING":
        return order

    mark_paid(order.pk)
    vendor_order = order.vendor_orders.get()
    if until == STATUS.PAID:
        return vendor_order

    if until == STATUS.CANCELLED:
        change_status(vendor_order.pk, STATUS.CANCELLED, vendor)
    else:
        for step in STEPS:
            change_status(vendor_order.pk, step, vendor)
            if step == until:
                break
    vendor_order.refresh_from_db()
    return vendor_order


def make_service(business, name="Dog Grooming"):
    return Service.objects.create(
        business=business,
        name=name,
        service_type="Grooming",
        description="Bath and trim",
        price=Decimal("30000.00"),
        duration=60,
        approved=True,
    )


def make_booking(customer, service, status=Booking.Status.COMPLETED, days=1):
    start = timezone.now() + timedelta(days=days)
    return Booking.objects.create(
        customer=customer,
        service=service,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status=status,
    )


def make_application(customer, pet, status=AdoptionApplication.Status.APPROVED):
    return AdoptionApplication.objects.create(
        pet=pet,
        customer=customer,
        status=status,
        home_type=AdoptionApplication.HomeType.HOUSE,
        previous_pet_experience=AdoptionApplication.Experience.SOME,
        message="I would love to adopt.",
    )


def add_review(customer, *, rating=5, comment="", visible=True, **target):
    """Insert a review directly, skipping the eligibility rules."""
    return Review.objects.create(
        customer=customer,
        rating=rating,
        comment=comment,
        is_visible=visible,
        **target,
    )


class ReviewTestCase(TestCase):
    """Shared world: two customers, a vendor with a business, an admin."""

    def setUp(self):
        self.customer = make_user("reviewer1", User.Role.CUSTOMER)
        self.other = make_user("reviewer2", User.Role.CUSTOMER)
        self.vendor = make_user("reviewvendor", User.Role.VENDOR)
        self.admin = make_user("reviewadmin", User.Role.ADMIN)
        self.business = make_business(self.vendor, name="Review Shop")
        self.category = make_category()
        self.product = make_product(
            self.business, self.category, name="Chew toy", price="10.00", stock=50
        )
        self.service = make_service(self.business)
        self.sale_pet = make_pet(self.vendor, self.business, name="Rex")
        self.adoption_pet = make_pet(
            self.vendor, self.business, name="Milo", listing_type="ADOPTION"
        )

        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def login(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def body(self, kind="product", target=None, rating=5, **extra):
        target = target or self.product
        return {"kind": kind, "target_id": target.pk, "rating": rating, **extra}


# --------------------------------------------------------------------------
# Database rules (the model constraints)
# --------------------------------------------------------------------------
class ReviewModelConstraintTests(ReviewTestCase):
    def test_a_review_with_no_target_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.create(customer=self.customer, rating=5)

    def test_a_review_with_two_targets_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.create(
                customer=self.customer,
                rating=5,
                product=self.product,
                service=self.service,
            )

    def test_rating_must_be_between_1_and_5(self):
        for bad in (0, 6):
            with self.subTest(rating=bad):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    add_review(self.customer, rating=bad, product=self.product)

    def test_one_review_per_customer_per_item(self):
        add_review(self.customer, product=self.product)
        with self.assertRaises(IntegrityError), transaction.atomic():
            add_review(self.customer, product=self.product)

    def test_two_customers_can_review_the_same_item(self):
        add_review(self.customer, product=self.product)
        add_review(self.other, product=self.product)
        self.assertEqual(Review.objects.count(), 2)

    def test_same_customer_can_review_different_kinds(self):
        add_review(self.customer, product=self.product)
        add_review(self.customer, service=self.service)
        add_review(self.customer, pet=self.sale_pet)
        self.assertEqual(Review.objects.filter(customer=self.customer).count(), 3)

    def test_target_kind_and_pk(self):
        review = add_review(self.customer, service=self.service)
        self.assertEqual(review.target_kind, "service")
        self.assertEqual(review.target_pk, self.service.pk)


# --------------------------------------------------------------------------
# Eligibility: products
# --------------------------------------------------------------------------
class ProductEligibilityTests(ReviewTestCase):
    def allowed(self, user=None):
        return check_eligibility(user or self.customer, "product", self.product)

    def test_delivered_order_can_review(self):
        buy(self.customer, self.vendor, product=self.product)
        self.assertEqual(self.allowed(), (True, ""))

    def test_never_bought_cannot_review(self):
        ok, reason = self.allowed()
        self.assertFalse(ok)
        self.assertIn("delivered", reason)

    def test_unpaid_order_cannot_review(self):
        buy(self.customer, self.vendor, product=self.product, until="PENDING")
        self.assertFalse(self.allowed()[0])

    def test_each_unfinished_status_cannot_review(self):
        for until in (STATUS.PAID, STATUS.PROCESSING, STATUS.SHIPPED):
            with self.subTest(status=until):
                customer = make_user(f"buyer-{until}", User.Role.CUSTOMER)
                buy(customer, self.vendor, product=self.product, until=until)
                self.assertFalse(self.allowed(customer)[0])

    def test_cancelled_order_cannot_review(self):
        buy(self.customer, self.vendor, product=self.product, until=STATUS.CANCELLED)
        self.assertFalse(self.allowed()[0])

    def test_someone_elses_delivery_does_not_count(self):
        buy(self.other, self.vendor, product=self.product)
        self.assertFalse(self.allowed(self.customer)[0])
        self.assertTrue(self.allowed(self.other)[0])

    def test_delivered_other_product_does_not_count(self):
        other_product = make_product(
            self.business, self.category, name="Ball", price="5.00", stock=10
        )
        buy(self.customer, self.vendor, product=other_product)
        self.assertFalse(self.allowed()[0])

    def test_already_reviewed_cannot_review_again(self):
        buy(self.customer, self.vendor, product=self.product)
        add_review(self.customer, product=self.product)
        ok, reason = self.allowed()
        self.assertFalse(ok)
        self.assertIn("already", reason)

    def test_vendor_and_admin_cannot_review(self):
        for user in (self.vendor, self.admin):
            with self.subTest(role=user.role):
                ok, reason = self.allowed(user)
                self.assertFalse(ok)
                self.assertIn("customers", reason)


# --------------------------------------------------------------------------
# Eligibility: services
# --------------------------------------------------------------------------
class ServiceEligibilityTests(ReviewTestCase):
    def allowed(self, user=None):
        return check_eligibility(user or self.customer, "service", self.service)

    def test_completed_booking_can_review(self):
        make_booking(self.customer, self.service, Booking.Status.COMPLETED)
        self.assertTrue(self.allowed()[0])

    def test_every_other_status_cannot_review(self):
        others = (
            Booking.Status.PENDING,
            Booking.Status.ACCEPTED,
            Booking.Status.DECLINED,
            Booking.Status.CANCELLED,
        )
        for index, status in enumerate(others):
            with self.subTest(status=status):
                customer = make_user(f"booker{index}", User.Role.CUSTOMER)
                make_booking(customer, self.service, status)
                self.assertFalse(self.allowed(customer)[0])

    def test_no_booking_cannot_review(self):
        ok, reason = self.allowed()
        self.assertFalse(ok)
        self.assertIn("booking", reason)

    def test_someone_elses_booking_does_not_count(self):
        make_booking(self.other, self.service, Booking.Status.COMPLETED)
        self.assertFalse(self.allowed(self.customer)[0])

    def test_completed_booking_of_another_service_does_not_count(self):
        other_service = make_service(self.business, name="Vet Check-up")
        make_booking(self.customer, other_service, Booking.Status.COMPLETED)
        self.assertFalse(self.allowed()[0])

    def test_already_reviewed_cannot_review_again(self):
        make_booking(self.customer, self.service, Booking.Status.COMPLETED)
        add_review(self.customer, service=self.service)
        self.assertFalse(self.allowed()[0])


# --------------------------------------------------------------------------
# Eligibility: pets (sale goes through checkout, adoption through application)
# --------------------------------------------------------------------------
class PetEligibilityTests(ReviewTestCase):
    def allowed(self, pet, user=None):
        return check_eligibility(user or self.customer, "pet", pet)

    # Sale pets
    def test_delivered_sale_pet_can_be_reviewed(self):
        buy(self.customer, self.vendor, pet=self.sale_pet)
        self.assertTrue(self.allowed(self.sale_pet)[0])

    def test_sale_pet_still_reserved_cannot_be_reviewed(self):
        buy(self.customer, self.vendor, pet=self.sale_pet, until="PENDING")
        self.assertFalse(self.allowed(self.sale_pet)[0])

    def test_paid_but_not_delivered_sale_pet_cannot_be_reviewed(self):
        for until in (STATUS.PAID, STATUS.PROCESSING, STATUS.SHIPPED):
            with self.subTest(status=until):
                pet = make_pet(self.vendor, self.business, name=f"Pet-{until}")
                customer = make_user(f"petbuyer-{until}", User.Role.CUSTOMER)
                buy(customer, self.vendor, pet=pet, until=until)
                self.assertFalse(self.allowed(pet, customer)[0])

    def test_cancelled_sale_pet_order_cannot_be_reviewed(self):
        buy(self.customer, self.vendor, pet=self.sale_pet, until=STATUS.CANCELLED)
        self.assertFalse(self.allowed(self.sale_pet)[0])

    def test_someone_else_bought_the_pet(self):
        buy(self.other, self.vendor, pet=self.sale_pet)
        self.assertFalse(self.allowed(self.sale_pet, self.customer)[0])
        self.assertTrue(self.allowed(self.sale_pet, self.other)[0])

    def test_an_approved_application_does_not_unlock_a_sale_pet(self):
        make_application(self.customer, self.sale_pet)
        self.assertFalse(self.allowed(self.sale_pet)[0])

    # Adoption pets
    def test_approved_adoption_can_be_reviewed(self):
        make_application(self.customer, self.adoption_pet)
        self.assertTrue(self.allowed(self.adoption_pet)[0])

    def test_other_application_statuses_cannot_review(self):
        others = (
            AdoptionApplication.Status.PENDING,
            AdoptionApplication.Status.INFO_REQUESTED,
            AdoptionApplication.Status.REJECTED,
            AdoptionApplication.Status.CANCELLED,
        )
        for index, status in enumerate(others):
            with self.subTest(status=status):
                customer = make_user(f"adopter{index}", User.Role.CUSTOMER)
                make_application(customer, self.adoption_pet, status)
                self.assertFalse(self.allowed(self.adoption_pet, customer)[0])

    def test_someone_elses_application_does_not_count(self):
        make_application(self.other, self.adoption_pet)
        self.assertFalse(self.allowed(self.adoption_pet, self.customer)[0])


# --------------------------------------------------------------------------
# Service layer: create_review, resolve_target, summary, with_ratings
# --------------------------------------------------------------------------
class CreateReviewServiceTests(ReviewTestCase):
    def test_creates_a_review_for_each_kind(self):
        buy(self.customer, self.vendor, product=self.product)
        make_booking(self.customer, self.service)
        make_application(self.customer, self.adoption_pet)

        cases = (
            ("product", self.product),
            ("service", self.service),
            ("pet", self.adoption_pet),
        )
        for kind, target in cases:
            with self.subTest(kind=kind):
                review = create_review(
                    customer=self.customer,
                    kind=kind,
                    target_id=target.pk,
                    rating=4,
                    comment="Nice",
                )
                self.assertEqual(review.target_kind, kind)
                self.assertEqual(review.rating, 4)

    def test_not_eligible_raises_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            create_review(
                customer=self.customer,
                kind="product",
                target_id=self.product.pk,
                rating=5,
            )
        self.assertEqual(Review.objects.count(), 0)

    def test_duplicate_is_refused(self):
        buy(self.customer, self.vendor, product=self.product)
        create_review(
            customer=self.customer, kind="product", target_id=self.product.pk, rating=5
        )
        with self.assertRaises(PermissionDenied):
            create_review(
                customer=self.customer,
                kind="product",
                target_id=self.product.pk,
                rating=1,
            )
        self.assertEqual(Review.objects.count(), 1)

    def test_a_double_click_race_becomes_a_clean_error(self):
        """Two requests pass the exists() check; the DB constraint stops one."""
        buy(self.customer, self.vendor, product=self.product)
        add_review(self.customer, product=self.product)
        with mock.patch("reviews.services.check_eligibility", return_value=(True, "")):
            with self.assertRaises(ValidationError):
                create_review(
                    customer=self.customer,
                    kind="product",
                    target_id=self.product.pk,
                    rating=5,
                )

    def test_resolve_target_rejects_unknown_kind(self):
        with self.assertRaises(ValidationError):
            resolve_target("spaceship", 1)

    def test_resolve_target_404_for_missing_item(self):
        from django.http import Http404

        with self.assertRaises(Http404):
            resolve_target("product", 999999)


class RatingSummaryTests(ReviewTestCase):
    def test_no_reviews(self):
        self.assertEqual(
            rating_summary("product", self.product),
            {"average_rating": None, "review_count": 0},
        )

    def test_average_is_rounded_to_one_decimal(self):
        for index, rating in enumerate((5, 4, 4)):
            customer = make_user(f"rater{index}", User.Role.CUSTOMER)
            add_review(customer, rating=rating, product=self.product)
        summary = rating_summary("product", self.product)
        self.assertEqual(summary["review_count"], 3)
        self.assertEqual(summary["average_rating"], 4.3)

    def test_hidden_reviews_are_left_out(self):
        add_review(self.customer, rating=5, product=self.product)
        add_review(self.other, rating=1, product=self.product, visible=False)
        self.assertEqual(
            rating_summary("product", self.product),
            {"average_rating": 5.0, "review_count": 1},
        )

    def test_other_items_do_not_leak_in(self):
        other = make_product(self.business, self.category, name="Ball", stock=5)
        add_review(self.customer, rating=1, product=other)
        self.assertEqual(rating_summary("product", self.product)["review_count"], 0)


class WithRatingsTests(ReviewTestCase):
    def test_annotates_products_services_and_pets(self):
        add_review(self.customer, rating=4, product=self.product)
        add_review(self.other, rating=2, product=self.product)
        add_review(self.customer, rating=5, service=self.service)
        add_review(self.customer, rating=3, pet=self.sale_pet)

        product = with_ratings(Product.objects.filter(pk=self.product.pk), "product").get()
        service = with_ratings(Service.objects.filter(pk=self.service.pk), "service").get()
        pet = with_ratings(Pet.objects.filter(pk=self.sale_pet.pk), "pet").get()

        self.assertEqual((product.average_rating, product.review_count), (3, 2))
        self.assertEqual((service.average_rating, service.review_count), (5, 1))
        self.assertEqual((pet.average_rating, pet.review_count), (3, 1))

    def test_items_without_reviews_have_zero_count_and_no_average(self):
        product = with_ratings(Product.objects.filter(pk=self.product.pk), "product").get()
        self.assertIsNone(product.average_rating)
        self.assertEqual(product.review_count, 0)

    def test_hidden_reviews_are_not_counted(self):
        add_review(self.customer, rating=5, product=self.product, visible=False)
        product = with_ratings(Product.objects.filter(pk=self.product.pk), "product").get()
        self.assertEqual(product.review_count, 0)

    def test_does_not_duplicate_rows(self):
        add_review(self.customer, rating=5, service=self.service)
        add_review(self.other, rating=5, service=self.service)
        rows = with_ratings(Service.objects.all(), "service")
        self.assertEqual(rows.count(), Service.objects.count())


# --------------------------------------------------------------------------
# API: create
# --------------------------------------------------------------------------
class CreateReviewAPITests(ReviewTestCase):
    url = property(lambda self: reverse("review-create"))

    def test_creates_a_review_after_delivery(self):
        buy(self.customer, self.vendor, product=self.product)

        response = self.client.post(
            self.url, self.body(rating=4, comment="Great toy"), format="json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["rating"], 4)
        self.assertEqual(response.data["comment"], "Great toy")
        self.assertEqual(response.data["kind"], "product")
        self.assertEqual(response.data["target_id"], self.product.pk)
        self.assertEqual(Review.objects.get().customer, self.customer)

    def test_comment_is_optional(self):
        buy(self.customer, self.vendor, product=self.product)
        response = self.client.post(self.url, self.body(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["comment"], "")

    def test_a_sold_pet_can_be_reviewed_after_delivery(self):
        buy(self.customer, self.vendor, pet=self.sale_pet)
        response = self.client.post(
            self.url, self.body("pet", self.sale_pet), format="json"
        )
        self.assertEqual(response.status_code, 201)

    def test_a_service_can_be_reviewed_after_a_completed_booking(self):
        make_booking(self.customer, self.service)
        response = self.client.post(
            self.url, self.body("service", self.service), format="json"
        )
        self.assertEqual(response.status_code, 201)

    def test_an_adoption_can_be_reviewed_after_approval(self):
        make_application(self.customer, self.adoption_pet)
        response = self.client.post(
            self.url, self.body("pet", self.adoption_pet), format="json"
        )
        self.assertEqual(response.status_code, 201)

    def test_not_delivered_is_403_with_a_reason(self):
        buy(self.customer, self.vendor, product=self.product, until=STATUS.SHIPPED)
        response = self.client.post(self.url, self.body(), format="json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("delivered", str(response.data["detail"]))
        self.assertEqual(Review.objects.count(), 0)

    def test_second_review_of_the_same_item_is_403(self):
        buy(self.customer, self.vendor, product=self.product)
        self.client.post(self.url, self.body(), format="json")
        response = self.client.post(self.url, self.body(rating=1), format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Review.objects.count(), 1)

    def test_anonymous_gets_401(self):
        response = APIClient().post(self.url, self.body(), format="json")
        self.assertEqual(response.status_code, 401)

    def test_vendor_cannot_review(self):
        response = self.login(self.vendor).post(self.url, self.body(), format="json")
        self.assertEqual(response.status_code, 403)

    def test_rating_must_be_1_to_5(self):
        buy(self.customer, self.vendor, product=self.product)
        for bad in (0, 6, -1, "abc"):
            with self.subTest(rating=bad):
                response = self.client.post(self.url, self.body(rating=bad), format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("rating", response.data)

    def test_rating_is_required(self):
        buy(self.customer, self.vendor, product=self.product)
        response = self.client.post(
            self.url, {"kind": "product", "target_id": self.product.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_comment_over_300_words_is_rejected(self):
        buy(self.customer, self.vendor, product=self.product)
        response = self.client.post(
            self.url, self.body(comment=" ".join(["word"] * 301)), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("comment", response.data)
        self.assertIn("300", str(response.data["comment"][0]))
        self.assertEqual(Review.objects.count(), 0)

    def test_comment_of_exactly_300_words_is_accepted(self):
        buy(self.customer, self.vendor, product=self.product)
        comment = " ".join(["word"] * 300)
        response = self.client.post(
            self.url, self.body(comment=comment), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["comment"], comment)

    def test_comment_over_1000_characters_is_fine_within_300_words(self):
        buy(self.customer, self.vendor, product=self.product)
        comment = " ".join(["abcdefghi"] * 200)  # 200 words, 1,999 characters
        self.assertGreater(len(comment), 1000)
        response = self.client.post(
            self.url, self.body(comment=comment), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Review.objects.get().comment, comment)

    def test_unknown_kind_is_400(self):
        response = self.client.post(
            self.url, {"kind": "car", "target_id": 1, "rating": 5}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_item_is_404(self):
        response = self.client.post(
            self.url, {"kind": "product", "target_id": 999999, "rating": 5}, format="json"
        )
        self.assertEqual(response.status_code, 404)


# --------------------------------------------------------------------------
# API: public list of an item's reviews
# --------------------------------------------------------------------------
class ReviewListAPITests(ReviewTestCase):
    def url(self, kind="product", target=None):
        target = target or self.product
        return reverse("review-list", kwargs={"kind": kind, "pk": target.pk})

    def test_is_public(self):
        add_review(self.customer, product=self.product)
        response = APIClient().get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_an_expired_token_does_not_break_the_public_page(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(client.get(self.url()).status_code, 200)

    def test_includes_summary_with_average_and_count(self):
        add_review(self.customer, rating=5, product=self.product)
        add_review(self.other, rating=4, product=self.product)
        response = APIClient().get(self.url())
        self.assertEqual(
            response.data["summary"], {"average_rating": 4.5, "review_count": 2}
        )

    def test_empty_item_has_a_null_average(self):
        response = APIClient().get(self.url())
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(
            response.data["summary"], {"average_rating": None, "review_count": 0}
        )

    def test_hidden_reviews_are_not_listed(self):
        add_review(self.customer, product=self.product)
        add_review(self.other, product=self.product, visible=False)
        response = APIClient().get(self.url())
        self.assertEqual(response.data["count"], 1)

    def test_only_this_items_reviews_are_listed(self):
        other = make_product(self.business, self.category, name="Ball", stock=5)
        add_review(self.customer, product=other)
        self.assertEqual(APIClient().get(self.url()).data["count"], 0)

    def test_works_for_services_and_pets(self):
        add_review(self.customer, service=self.service)
        add_review(self.customer, pet=self.sale_pet)
        self.assertEqual(APIClient().get(self.url("service", self.service)).data["count"], 1)
        self.assertEqual(APIClient().get(self.url("pet", self.sale_pet)).data["count"], 1)

    def test_a_sold_pet_still_shows_its_reviews(self):
        buy(self.customer, self.vendor, pet=self.sale_pet)
        self.sale_pet.refresh_from_db()
        self.assertEqual(self.sale_pet.adoption_status, Pet.AdoptionStatus.SOLD)
        add_review(self.customer, pet=self.sale_pet)
        self.assertEqual(APIClient().get(self.url("pet", self.sale_pet)).data["count"], 1)

    def test_is_paginated(self):
        for index in range(3):
            customer = make_user(f"pager{index}", User.Role.CUSTOMER)
            add_review(customer, product=self.product)
        response = APIClient().get(self.url(), {"page_size": 2})
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])

    def test_newest_first(self):
        first = add_review(self.customer, product=self.product, comment="old")
        second = add_review(self.other, product=self.product, comment="new")
        Review.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        results = APIClient().get(self.url()).data["results"]
        self.assertEqual([r["id"] for r in results], [second.pk, first.pk])

    def test_unknown_kind_is_400_and_missing_item_is_404(self):
        self.assertEqual(
            APIClient().get(reverse("review-list", kwargs={"kind": "car", "pk": 1})).status_code,
            400,
        )
        self.assertEqual(
            APIClient()
            .get(reverse("review-list", kwargs={"kind": "product", "pk": 999999}))
            .status_code,
            404,
        )

    def test_reviewer_name_is_shortened_and_private_data_is_not_exposed(self):
        self.customer.first_name, self.customer.last_name = "Jane", "Doe"
        self.customer.save()
        add_review(self.customer, product=self.product)

        review = APIClient().get(self.url()).data["results"][0]

        self.assertEqual(review["reviewer"], "Jane D.")
        for private in ("customer", "email", "customer_id", "is_visible"):
            self.assertNotIn(private, review)

    def test_reviewer_without_a_name_is_called_customer(self):
        self.customer.first_name = ""
        self.customer.save()
        add_review(self.customer, product=self.product)
        self.assertEqual(
            APIClient().get(self.url()).data["results"][0]["reviewer"], "Customer"
        )


# --------------------------------------------------------------------------
# API: my reviews, can-review, edit/delete, admin hide
# --------------------------------------------------------------------------
class MyReviewsAPITests(ReviewTestCase):
    def test_lists_only_my_reviews(self):
        add_review(self.customer, product=self.product)
        add_review(self.other, service=self.service)
        response = self.client.get(reverse("review-mine"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["kind"], "product")

    def test_includes_my_hidden_reviews(self):
        add_review(self.customer, product=self.product, visible=False)
        self.assertEqual(self.client.get(reverse("review-mine")).data["count"], 1)

    def test_requires_login(self):
        self.assertEqual(APIClient().get(reverse("review-mine")).status_code, 401)


class CanReviewAPITests(ReviewTestCase):
    url = property(lambda self: reverse("review-can-review"))

    def ask(self, kind, target, client=None):
        return (client or self.client).get(self.url, {"kind": kind, "id": target.pk})

    def test_false_before_delivery_with_a_reason(self):
        response = self.ask("product", self.product)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["can_review"])
        self.assertTrue(response.data["reason"])

    def test_true_after_delivery(self):
        buy(self.customer, self.vendor, product=self.product)
        response = self.ask("product", self.product)
        self.assertTrue(response.data["can_review"])
        self.assertEqual(response.data["reason"], "")

    def test_false_after_reviewing(self):
        buy(self.customer, self.vendor, product=self.product)
        add_review(self.customer, product=self.product)
        self.assertFalse(self.ask("product", self.product).data["can_review"])

    def test_agrees_with_create_for_every_kind(self):
        make_booking(self.customer, self.service)
        make_application(self.customer, self.adoption_pet)
        buy(self.customer, self.vendor, pet=self.sale_pet)
        for kind, target in (
            ("service", self.service),
            ("pet", self.adoption_pet),
            ("pet", self.sale_pet),
        ):
            with self.subTest(kind=kind, target=target.pk):
                self.assertTrue(self.ask(kind, target).data["can_review"])

    def test_vendor_is_told_no(self):
        response = self.ask("product", self.product, self.login(self.vendor))
        self.assertFalse(response.data["can_review"])

    def test_requires_login(self):
        self.assertEqual(self.ask("product", self.product, APIClient()).status_code, 401)

    def test_bad_input(self):
        self.assertEqual(
            self.client.get(self.url, {"kind": "car", "id": 1}).status_code, 400
        )
        self.assertEqual(
            self.client.get(self.url, {"kind": "product", "id": 999999}).status_code, 404
        )


class EditAndDeleteReviewAPITests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.review = add_review(
            self.customer, rating=3, comment="ok", product=self.product
        )
        self.url = reverse("review-detail", kwargs={"pk": self.review.pk})

    def test_author_can_edit_rating_and_comment(self):
        response = self.client.patch(
            self.url, {"rating": 5, "comment": "better"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.review.refresh_from_db()
        self.assertEqual((self.review.rating, self.review.comment), (5, "better"))

    def test_edit_can_change_just_one_field(self):
        self.client.patch(self.url, {"rating": 1}, format="json")
        self.review.refresh_from_db()
        self.assertEqual((self.review.rating, self.review.comment), (1, "ok"))

    def test_edit_cannot_move_the_review_to_another_item_or_user(self):
        other_product = make_product(self.business, self.category, name="Ball", stock=5)
        self.client.patch(
            self.url,
            {"product": other_product.pk, "customer": self.other.pk, "is_visible": False},
            format="json",
        )
        self.review.refresh_from_db()
        self.assertEqual(self.review.product, self.product)
        self.assertEqual(self.review.customer, self.customer)
        self.assertTrue(self.review.is_visible)

    def test_edit_validates_rating(self):
        response = self.client.patch(self.url, {"rating": 9}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_edit_over_300_words_is_rejected_and_nothing_changes(self):
        response = self.client.patch(
            self.url, {"comment": " ".join(["word"] * 301)}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("comment", response.data)
        self.assertIn("300", str(response.data["comment"][0]))
        self.review.refresh_from_db()
        self.assertEqual(self.review.comment, "ok")

    def test_edit_to_exactly_300_words_is_accepted(self):
        comment = " ".join(["word"] * 300)
        response = self.client.patch(self.url, {"comment": comment}, format="json")
        self.assertEqual(response.status_code, 200)
        self.review.refresh_from_db()
        self.assertEqual(self.review.comment, comment)

    def test_edit_to_more_than_1000_characters_is_fine_within_300_words(self):
        comment = " ".join(["abcdefghi"] * 200)  # 200 words, 1,999 characters
        response = self.client.patch(self.url, {"comment": comment}, format="json")
        self.assertEqual(response.status_code, 200)
        self.review.refresh_from_db()
        self.assertEqual(self.review.comment, comment)

    def test_someone_else_gets_404_and_nothing_changes(self):
        other_client = self.login(self.other)
        self.assertEqual(
            other_client.patch(self.url, {"rating": 1}, format="json").status_code, 404
        )
        self.assertEqual(other_client.delete(self.url).status_code, 404)
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 3)

    def test_put_is_not_allowed(self):
        response = self.client.put(self.url, {"rating": 4}, format="json")
        self.assertEqual(response.status_code, 405)

    def test_author_can_delete_and_then_review_again(self):
        buy(self.customer, self.vendor, product=self.product)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Review.objects.filter(pk=self.review.pk).exists())
        again = self.client.post(
            reverse("review-create"), self.body(rating=2), format="json"
        )
        self.assertEqual(again.status_code, 201)

    def test_requires_login(self):
        self.assertEqual(APIClient().delete(self.url).status_code, 401)


class AdminHideReviewAPITests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.review = add_review(self.customer, rating=1, product=self.product)
        self.url = reverse("review-visibility", kwargs={"pk": self.review.pk})

    def test_admin_can_hide_and_restore(self):
        admin = self.login(self.admin)

        hidden = admin.patch(self.url, {"is_visible": False}, format="json")
        self.assertEqual(hidden.status_code, 200)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_visible)

        restored = admin.patch(self.url, {"is_visible": True}, format="json")
        self.assertEqual(restored.status_code, 200)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_visible)

    def test_hiding_removes_it_from_the_public_list_and_the_average(self):
        public_url = reverse(
            "review-list", kwargs={"kind": "product", "pk": self.product.pk}
        )
        self.assertEqual(APIClient().get(public_url).data["summary"]["review_count"], 1)

        self.login(self.admin).patch(self.url, {"is_visible": False}, format="json")

        data = APIClient().get(public_url).data
        self.assertEqual(data["count"], 0)
        self.assertEqual(
            data["summary"], {"average_rating": None, "review_count": 0}
        )

    def test_hidden_review_still_blocks_a_second_review(self):
        buy(self.customer, self.vendor, product=self.product)
        self.login(self.admin).patch(self.url, {"is_visible": False}, format="json")
        response = self.client.post(
            reverse("review-create"), self.body(), format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_customer_and_vendor_cannot_hide(self):
        for user in (self.customer, self.vendor):
            with self.subTest(role=user.role):
                response = self.login(user).patch(
                    self.url, {"is_visible": False}, format="json"
                )
                self.assertEqual(response.status_code, 403)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_visible)

    def test_anonymous_gets_401(self):
        response = APIClient().patch(self.url, {"is_visible": False}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_bad_input_and_unknown_review(self):
        admin = self.login(self.admin)
        self.assertEqual(admin.patch(self.url, {}, format="json").status_code, 400)
        missing = reverse("review-visibility", kwargs={"pk": 999999})
        self.assertEqual(
            admin.patch(missing, {"is_visible": False}, format="json").status_code, 404
        )


# --------------------------------------------------------------------------
# API: reply creation permissions (Commit 1)
# --------------------------------------------------------------------------
class ReviewReplyCreatePermissionTests(ReviewTestCase):
    """POST /reviews/<pk>/replies/ must be restricted to authenticated vendors."""

    def setUp(self):
        super().setUp()
        self.review = add_review(self.customer, product=self.product)
        self.url = reverse("review-replies", kwargs={"pk": self.review.pk})
        self.payload = {"body": "Thank you for your feedback!"}

    def test_authenticated_vendor_can_post_a_reply(self):
        response = self.login(self.vendor).post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 201)
        reply = ReviewReply.objects.get()
        self.assertEqual(reply.author, self.vendor)
        self.assertEqual(reply.review, self.review)
        self.assertEqual(response.data["id"], reply.pk)
        self.assertEqual(response.data["review_id"], self.review.pk)

        public_url = reverse(
            "review-list", kwargs={"kind": "product", "pk": self.product.pk}
        )
        public_response = APIClient().get(public_url)
        self.assertEqual(public_response.status_code, 200)
        public_review = next(
            result
            for result in public_response.data["results"]
            if result["id"] == self.review.pk
        )
        self.assertEqual(public_review["replies"][0]["id"], reply.pk)
        self.assertEqual(public_review["replies"][0]["body"], self.payload["body"])

    def test_vendor_cannot_post_a_duplicate_reply(self):
        client = self.login(self.vendor)
        first_response = client.post(self.url, self.payload, format="json")
        self.assertEqual(first_response.status_code, 201)

        duplicate_response = client.post(
            self.url, {"body": "A second reply."}, format="json"
        )

        self.assertEqual(duplicate_response.status_code, 400)
        self.assertEqual(ReviewReply.objects.count(), 1)
        reply = ReviewReply.objects.get()
        self.assertEqual(reply.review, self.review)
        self.assertEqual(reply.body, self.payload["body"])

    def test_anonymous_post_returns_401_and_creates_no_reply(self):
        response = APIClient().post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(ReviewReply.objects.count(), 0)

    def test_customer_post_returns_403_and_creates_no_reply(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ReviewReply.objects.count(), 0)

    def test_admin_post_returns_403_and_creates_no_reply(self):
        response = self.login(self.admin).post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ReviewReply.objects.count(), 0)

    def test_get_replies_is_public_without_authentication(self):
        response = APIClient().get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_get_replies_tolerates_an_expired_token(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(client.get(self.url).status_code, 200)


# --------------------------------------------------------------------------
# Service layer: create_reply
# --------------------------------------------------------------------------
class CreateReplyServiceTests(ReviewTestCase):
    """Service-level tests for vendor ownership and one-reply-per-review rules."""

    def setUp(self):
        super().setUp()
        self.review = add_review(self.customer, product=self.product)
        self.other_vendor = make_user("othervendor", User.Role.VENDOR)
        self.other_business = make_business(self.other_vendor, name="Other Shop")

    def test_vendor_cannot_reply_to_another_vendors_review(self):
        with self.assertRaises(PermissionDenied):
            create_reply(
                author=self.other_vendor,
                review_id=self.review.pk,
                body="Trying to reply to someone else's review.",
            )
        self.assertEqual(ReviewReply.objects.count(), 0)

    def test_vendor_can_reply_to_their_own_business_review(self):
        reply = create_reply(
            author=self.vendor,
            review_id=self.review.pk,
            body="Thank you for your feedback!",
        )
        self.assertEqual(reply.author, self.vendor)
        self.assertEqual(reply.review, self.review)
        self.assertEqual(ReviewReply.objects.count(), 1)

    def test_vendor_cannot_reply_twice_to_the_same_review(self):
        create_reply(
            author=self.vendor,
            review_id=self.review.pk,
            body="First reply.",
        )
        with self.assertRaises(ValidationError) as ctx:
            create_reply(
                author=self.vendor,
                review_id=self.review.pk,
                body="Second reply.",
            )
        self.assertIn("body", ctx.exception.detail)
        self.assertEqual(ReviewReply.objects.count(), 1)

    def test_vendor_can_reply_to_a_different_review(self):
        second_review = add_review(self.other, product=self.product)
        create_reply(
            author=self.vendor,
            review_id=self.review.pk,
            body="Reply to first review.",
        )
        reply2 = create_reply(
            author=self.vendor,
            review_id=second_review.pk,
            body="Reply to second review.",
        )
        self.assertEqual(ReviewReply.objects.count(), 2)
        self.assertEqual(reply2.review, second_review)


# --------------------------------------------------------------------------
# Serializer: replies embedded in ReviewSerializer (Commit 3)
# --------------------------------------------------------------------------
class ReviewSerializerRepliesTests(ReviewTestCase):
    """ReviewSerializer must embed associated replies in its output."""

    def setUp(self):
        super().setUp()
        self.review = add_review(self.customer, product=self.product)
        self.url = reverse("review-replies", kwargs={"pk": self.review.pk})

    def _review_data(self):
        """Fetch the review via the public list endpoint and return the first result."""
        list_url = reverse("review-list", kwargs={"kind": "product", "pk": self.product.pk})
        return APIClient().get(list_url).data["results"][0]

    def test_review_with_no_replies_returns_empty_list(self):
        data = self._review_data()
        self.assertIn("replies", data)
        self.assertEqual(data["replies"], [])

    def test_review_response_includes_associated_reply(self):
        self.vendor.first_name = "Alice"
        self.vendor.last_name = "Smith"
        self.vendor.save()
        reply = create_reply(
            author=self.vendor,
            review_id=self.review.pk,
            body="Thank you for your feedback!",
        )

        data = self._review_data()
        self.assertEqual(len(data["replies"]), 1)
        r = data["replies"][0]
        self.assertEqual(r["id"], reply.pk)
        self.assertEqual(r["body"], "Thank you for your feedback!")
        self.assertEqual(r["author_name"], "Alice S.")
        self.assertEqual(r["author_role"], str(self.vendor.role))
        self.assertIn("created_at", r)

    def test_reply_fields_match_review_reply_serializer_output(self):
        create_reply(author=self.vendor, review_id=self.review.pk, body="Great choice!")

        data = self._review_data()
        r = data["replies"][0]
        self.assertEqual(
            set(r.keys()), {"id", "review_id", "author_name", "author_role", "body", "created_at"}
        )
        self.assertEqual(r["review_id"], self.review.pk)


# --------------------------------------------------------------------------
# Query count: prefetch_related prevents N+1 on review list (Commit 4)
# --------------------------------------------------------------------------
class ReviewListQueryCountTests(ReviewTestCase):
    """Fetching multiple reviews with replies must not produce N+1 queries."""

    def setUp(self):
        super().setUp()
        customer = make_user("qc_customer0", User.Role.CUSTOMER)
        self.reviews = [add_review(customer, product=self.product)]
        create_reply(author=self.vendor, review_id=self.reviews[0].pk, body="Thanks!")

    def test_review_list_with_replies_does_not_produce_n_plus_1_queries(self):
        list_url = reverse("review-list", kwargs={"kind": "product", "pk": self.product.pk})

        with CaptureQueriesContext(connection) as one_review_queries:
            one_review_response = APIClient().get(list_url)

        self.assertEqual(one_review_response.status_code, 200)
        one_review_results = one_review_response.data["results"]
        self.assertEqual(len(one_review_results), 1)
        self.assertEqual(one_review_results[0]["replies"][0]["body"], "Thanks!")

        for index in range(1, 3):
            customer = make_user(f"qc_customer{index}", User.Role.CUSTOMER)
            review = add_review(customer, product=self.product)
            self.reviews.append(review)
            create_reply(author=self.vendor, review_id=review.pk, body="Thanks!")

        with CaptureQueriesContext(connection) as multiple_review_queries:
            multiple_review_response = APIClient().get(list_url)

        self.assertEqual(multiple_review_response.status_code, 200)
        multiple_review_results = multiple_review_response.data["results"]
        self.assertEqual(len(multiple_review_results), 3)
        self.assertTrue(all(result["replies"] for result in multiple_review_results))
        self.assertTrue(
            all(result["replies"][0]["body"] == "Thanks!" for result in multiple_review_results)
        )

        self.assertEqual(
            len(one_review_queries),
            len(multiple_review_queries),
            "Query count grew when adding a review with a reply — N+1 detected.",
        )


# --------------------------------------------------------------------------
# Serializers: the 300-word comment limit (create and edit share one rule)
# --------------------------------------------------------------------------
def words(n, size=5):
    return " ".join(["a" * size] * n)


def build_create(comment):
    data = {"kind": "product", "target_id": 1, "rating": 5}
    if comment is not None:
        data["comment"] = comment
    return ReviewCreateSerializer(data=data)


def build_update(comment):
    data = {} if comment is None else {"comment": comment}
    return ReviewUpdateSerializer(data=data, partial=True)


BUILDERS = (("create", build_create), ("update", build_update))


class CommentWordLimitTests(SimpleTestCase):
    """Submitting and editing a review apply exactly the same rule."""

    def assert_accepted(self, comment):
        for name, build in BUILDERS:
            with self.subTest(name):
                serializer = build(comment)
                self.assertTrue(serializer.is_valid(), serializer.errors)

    def assert_rejected(self, comment):
        for name, build in BUILDERS:
            with self.subTest(name):
                serializer = build(comment)
                self.assertFalse(serializer.is_valid())
                self.assertEqual(set(serializer.errors), {"comment"})

    def test_count_words(self):
        cases = [
            ("", 0),
            ("   ", 0),
            ("one", 1),
            ("one two", 2),
            ("  one   two  ", 2),
            ("one\ntwo\tthree", 3),
            ("well-made don't", 2),
            ("a\u00a0b", 2),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(count_words(text), expected)

    def test_exactly_300_words_is_accepted(self):
        self.assert_accepted(words(MAX_COMMENT_WORDS))

    def test_301_words_is_rejected_with_a_clear_message(self):
        self.assert_rejected(words(MAX_COMMENT_WORDS + 1))
        for name, build in BUILDERS:
            with self.subTest(name):
                serializer = build(words(MAX_COMMENT_WORDS + 1))
                serializer.is_valid()
                message = str(serializer.errors["comment"][0])
                self.assertIn("300", message)
                self.assertIn("301", message)

    def test_the_old_1000_character_limit_no_longer_applies(self):
        comment = words(200, size=9)  # 200 words, 1,999 characters
        self.assertGreater(len(comment), 1000)
        self.assert_accepted(comment)

    def test_whitespace_runs_count_as_one_separator(self):
        self.assert_accepted(" \n\t ".join(["word"] * MAX_COMMENT_WORDS))

    def test_surrounding_whitespace_is_ignored_and_stripped(self):
        for name, build in BUILDERS:
            with self.subTest(name):
                serializer = build("  " + words(MAX_COMMENT_WORDS) + "\n\n")
                self.assertTrue(serializer.is_valid(), serializer.errors)
                self.assertEqual(
                    serializer.validated_data["comment"], words(MAX_COMMENT_WORDS)
                )

    def test_comment_is_optional_and_may_be_blank(self):
        for comment in ("", "   ", None):
            with self.subTest(comment=comment):
                self.assert_accepted(comment)

    def test_one_enormous_word_hits_the_safety_cap(self):
        self.assert_accepted("x" * MAX_COMMENT_CHARS)
        self.assert_rejected("x" * (MAX_COMMENT_CHARS + 1))

    def test_update_without_a_comment_is_valid(self):
        serializer = ReviewUpdateSerializer(data={"rating": 4}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_create_still_validates_the_other_fields(self):
        serializer = ReviewCreateSerializer(
            data={"kind": "product", "target_id": 1, "rating": 6, "comment": "ok"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertEqual(set(serializer.errors), {"rating"})