from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from products.models import Product


class ProductViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="product_vendor",
            email="vendor@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.another_vendor = User.objects.create_user(
            username="another_vendor",
            email="another-vendor@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.admin = User.objects.create_user(
            username="product_admin",
            email="admin@example.com",
            password="test-password-123",
            role=User.Role.ADMIN,
        )
        cls.system_admin = User.objects.create_user(
            username="product_system_admin",
            email="system-admin@example.com",
            password="test-password-123",
            role=User.Role.SYSTEM_ADMIN,
        )
        cls.customer = User.objects.create_user(
            username="product_customer",
            email="customer@example.com",
            password="test-password-123",
            role=User.Role.CUSTOMER,
        )

        cls.category = Category.objects.create(name="Pet Supplies")
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Product Test Business",
            description="Pet supplies and accessories",
            contact="+256700000001",
            email="product-business@example.com",
            address="Kampala",
            city_district="Central",
            business_type=Business.BusinessType.PRODUCT_SELLER,
            verification_status=Business.VerificationStatus.APPROVED,
            is_active=True,
        )
        cls.another_business = Business.objects.create(
            vendor=cls.another_vendor,
            name="Another Product Business",
            description="Other pet supplies",
            contact="+256700000002",
            email="another-product-business@example.com",
            address="Entebbe",
            city_district="Wakiso",
            business_type=Business.BusinessType.PRODUCT_SELLER,
            verification_status=Business.VerificationStatus.APPROVED,
            is_active=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.list_url = reverse("product-list")

    def create_product(
        self, vendor=None, name="Rubber Ball", is_active=True, approved=True
    ):
        business = (
            self.another_business if vendor == self.another_vendor
            else self.business
        )
        return Product.objects.create(
            business=business,
            category=self.category,
            name=name,
            description="A durable pet toy.",
            price="15000.00",
            is_active=is_active,
            approved=approved,
        )

    def get_results(self, response):
        if isinstance(response.data, dict) and "results" in response.data:
            return response.data["results"]

        return response.data

    def create_business(self, name, vendor=None, **overrides):
        values = {
            "vendor": vendor or self.vendor,
            "description": "Extra test business",
            "contact": "+256700000003",
            "email": "extra-business@example.com",
            "address": "Kampala",
            "city_district": "Central",
            "business_type": Business.BusinessType.PRODUCT_SELLER,
            "verification_status": Business.VerificationStatus.APPROVED,
            "is_active": True,
        }
        values.update(overrides)
        return Business.objects.create(name=name, **values)

    def test_anonymous_user_can_list_active_products(self):
        active = self.create_product(name="Active Ball")
        self.create_product(name="Inactive Ball", is_active=False)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in self.get_results(response)],
            [active.pk],
        )

    def test_admin_can_list_inactive_products(self):
        active = self.create_product(name="Active Toy")
        inactive = self.create_product(
            name="Inactive Toy",
            is_active=False,
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in self.get_results(response)},
            {active.pk, inactive.pk},
        )

    def test_vendor_can_only_list_own_products(self):
        own_product = self.create_product(name="Own Product")
        other_product = self.create_product(
            vendor=self.another_vendor,
            name="Other Vendor Product",
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product_ids = {
            product["id"] for product in self.get_results(response)
        }
        self.assertIn(own_product.pk, product_ids)
        self.assertNotIn(other_product.pk, product_ids)

    def test_admin_can_retrieve_inactive_product(self):
        product = self.create_product(is_active=False)
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            reverse("product-detail", kwargs={"pk": product.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], product.pk)

    def test_admin_can_create_product(self):
        payload = {
            "business": self.business.pk,
            "category": self.category.pk,
            "name": "New Product",
            "description": "A newly managed product.",
            "price": "12000.00",
            "is_active": True,
        }
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Product.objects.filter(name="New Product").exists())

    def test_admin_cannot_create_product_with_zero_price(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            {
                "business": self.business.pk,
                "category": self.category.pk,
                "name": "Zero Price Product",
                "price": "0.00",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            Product.objects.filter(name="Zero Price Product").exists()
        )

    def test_admin_cannot_create_product_with_negative_price(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            {
                "business": self.business.pk,
                "category": self.category.pk,
                "name": "Negative Price Product",
                "price": "-10.00",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            Product.objects.filter(name="Negative Price Product").exists()
        )

    def test_system_admin_can_create_product(self):
        self.client.force_authenticate(user=self.system_admin)

        response = self.client.post(
            self.list_url,
            {
                "business": self.business.pk,
                "category": self.category.pk,
                "name": "System Admin Product",
                "price": "12000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_admin_can_update_product(self):
        product = self.create_product()
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            reverse("product-detail", kwargs={"pk": product.pk}),
            {"name": "Updated Rubber Ball"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertEqual(product.name, "Updated Rubber Ball")

    def test_admin_deletes_product_by_deactivating_it(self):
        product = self.create_product()
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(
            reverse("product-detail", kwargs={"pk": product.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    def test_vendor_can_deactivate_own_product(self):
        product = self.create_product()
        self.client.force_authenticate(user=self.vendor)

        response = self.client.delete(
            reverse("product-detail", kwargs={"pk": product.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        product.refresh_from_db()
        self.assertFalse(product.is_active)

    def test_vendor_cannot_deactivate_another_vendors_product(self):
        product = self.create_product(vendor=self.another_vendor)
        self.client.force_authenticate(user=self.vendor)

        response = self.client.delete(
            reverse("product-detail", kwargs={"pk": product.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        product.refresh_from_db()
        self.assertTrue(product.is_active)

    def test_vendor_can_create_product_for_own_business(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.list_url,
            {
                "business": self.business.pk,
                "category": self.category.pk,
                "name": "Vendor Product",
                "description": "A vendor-managed product.",
                "price": "12000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Product.objects.filter(
                name="Vendor Product",
                business=self.business,
            ).exists()
        )

    def test_vendor_cannot_create_product_for_another_business(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.list_url,
            {
                "business": self.another_business.pk,
                "category": self.category.pk,
                "name": "Unauthorized Product",
                "price": "12000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            Product.objects.filter(name="Unauthorized Product").exists()
        )

    def test_vendor_can_retrieve_own_product(self):
        product = self.create_product()
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(
            reverse("product-detail", kwargs={"pk": product.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], product.pk)

    def test_vendor_cannot_retrieve_another_vendors_product(self):
        product = self.create_product(vendor=self.another_vendor)
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(
            reverse("product-detail", kwargs={"pk": product.pk})
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_vendor_can_update_own_product(self):
        product = self.create_product()
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(
            reverse("product-detail", kwargs={"pk": product.pk}),
            {"name": "Vendor Updated Product"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertEqual(product.name, "Vendor Updated Product")

    def test_vendor_cannot_update_another_vendors_product(self):
        product = self.create_product(vendor=self.another_vendor)
        original_name = product.name
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(
            reverse("product-detail", kwargs={"pk": product.pk}),
            {"name": "Unauthorized Update"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        product.refresh_from_db()
        self.assertEqual(product.name, original_name)

    def test_vendor_cannot_reassign_own_product_to_another_business(self):
        product = self.create_product()
        original_business = product.business
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(
            reverse("product-detail", kwargs={"pk": product.pk}),
            {"business": self.another_business.pk},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        product.refresh_from_db()
        self.assertEqual(product.business, original_business)

    def test_customer_cannot_update_product(self):
        product = self.create_product()
        self.client.force_authenticate(user=self.customer)

        response = self.client.patch(
            reverse("product-detail", kwargs={"pk": product.pk}),
            {"name": "Unauthorized Change"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_anonymous_user_cannot_create_product(self):
        response = self.client.post(
            self.list_url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_non_admin_cannot_retrieve_inactive_product(self):
        product = self.create_product(is_active=False)

        response = self.client.get(
            reverse("product-detail", kwargs={"pk": product.pk})
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_vendor_cannot_create_product_for_pending_business(self):
        pending_business = self.create_business(
            "Pending Business",
            verification_status=Business.VerificationStatus.PENDING,
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.list_url,
            {
                "business": pending_business.pk,
                "category": self.category.pk,
                "name": "Pending Business Product",
                "price": "12000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("business", response.data)
        self.assertFalse(
            Product.objects.filter(name="Pending Business Product").exists()
        )

    def test_vendor_cannot_create_product_for_service_provider_business(self):
        service_business = self.create_business(
            "Service Provider Business",
            business_type=Business.BusinessType.SERVICE_PROVIDER,
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.list_url,
            {
                "business": service_business.pk,
                "category": self.category.pk,
                "name": "Service Business Product",
                "price": "12000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("business", response.data)
        self.assertFalse(
            Product.objects.filter(name="Service Business Product").exists()
        )

    def test_anonymous_user_cannot_see_products_from_unapproved_business(self):
        pending_business = self.create_business(
            "Hidden Business",
            verification_status=Business.VerificationStatus.PENDING,
        )
        product = Product.objects.create(
            business=pending_business,
            category=self.category,
            name="Hidden Product",
            price="15000.00",
        )

        list_response = self.client.get(self.list_url)
        detail_response = self.client.get(
            reverse("product-detail", kwargs={"pk": product.pk})
        )

        self.assertNotIn(
            product.pk,
            [item["id"] for item in self.get_results(list_response)],
        )
        self.assertEqual(
            detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_anonymous_user_cannot_see_products_in_inactive_category(self):
        inactive_category = Category.objects.create(
            name="Retired Category",
            is_active=False,
        )
        product = Product.objects.create(
            business=self.business,
            category=inactive_category,
            name="Retired Category Product",
            price="15000.00",
        )

        list_response = self.client.get(self.list_url)
        detail_response = self.client.get(
            reverse("product-detail", kwargs={"pk": product.pk})
        )

        self.assertNotIn(
            product.pk,
            [item["id"] for item in self.get_results(list_response)],
        )
        self.assertEqual(
            detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_vendor_can_still_edit_product_after_business_is_suspended(self):
        product = self.create_product()
        Business.objects.filter(pk=self.business.pk).update(
            verification_status=Business.VerificationStatus.SUSPENDED,
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(
            reverse("product-detail", kwargs={"pk": product.pk}),
            {"name": "Edited While Suspended"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertEqual(product.name, "Edited While Suspended")

    def test_vendor_can_see_stock_quantity_on_own_product(self):
        product = self.create_product()
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(
            reverse("product-detail", kwargs={"pk": product.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("stock_quantity", response.data)

    def post_product_with_category(self, category):
        self.client.force_authenticate(user=self.vendor)
        return self.client.post(
            self.list_url,
            {
                "business": self.business.pk,
                "category": category.pk,
                "name": "Kind Test Product",
                "price": "12000.00",
            },
            format="json",
        )

    def test_vendor_can_create_product_in_merchandise_category(self):
        category = Category.objects.create(
            name="Merchandise Kind",
            kind=Category.Kind.MERCHANDISE,
        )

        response = self.post_product_with_category(category)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_vendor_can_create_product_in_general_category(self):
        category = Category.objects.create(
            name="General Kind",
            kind=Category.Kind.GENERAL,
        )

        response = self.post_product_with_category(category)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_vendor_cannot_create_product_in_services_category(self):
        category = Category.objects.create(
            name="Services Kind",
            kind=Category.Kind.SERVICES,
        )

        response = self.post_product_with_category(category)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)
        self.assertFalse(
            Product.objects.filter(name="Kind Test Product").exists()
        )

    def test_vendor_cannot_create_product_in_pets_category(self):
        category = Category.objects.create(
            name="Pets Kind",
            kind=Category.Kind.PETS,
        )

        response = self.post_product_with_category(category)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)
        self.assertFalse(
            Product.objects.filter(name="Kind Test Product").exists()
        )