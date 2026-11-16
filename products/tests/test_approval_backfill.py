import importlib

from django.apps import apps
from django.test import TestCase

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from products.models import Product

migration = importlib.import_module(
    "products.migrations.0004_approve_existing_products"
)


class ApproveExistingProductsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        vendor = User.objects.create_user(
            username="backfill_vendor",
            email="backfill@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.business = Business.objects.create(
            vendor=vendor,
            name="Backfill Merch",
            description="Backfill test",
            contact="+256700000001",
            email="backfill-merch@example.com",
            address="Kampala",
            city_district="Central",
            business_type=Business.BusinessType.PRODUCT_SELLER,
            verification_status=Business.VerificationStatus.APPROVED,
        )
        cls.category = Category.objects.create(kind=Category.Kind.MERCHANDISE, name="Backfill Supplies")

    def make_product(self, name, **overrides):
        return Product.objects.create(
            business=self.business,
            category=self.category,
            name=name,
            price="1000",
            **overrides,
        )

    def test_unreviewed_products_become_approved(self):
        product = self.make_product("Old Product")
        self.assertFalse(product.approved)

        migration.approve_existing_products(apps, None)

        product.refresh_from_db()
        self.assertTrue(product.approved)

    def test_rejected_products_stay_unapproved(self):
        product = self.make_product("Rejected", rejection_reason="Bad photo")

        migration.approve_existing_products(apps, None)

        product.refresh_from_db()
        self.assertFalse(product.approved)
