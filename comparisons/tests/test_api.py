from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from pets.models import Pet
from products.models import Product
from services.models import Service


class ListingComparisonAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("listing-comparison")
        self.vendor = self.make_vendor("comparison_vendor")
        self.other_vendor = self.make_vendor("comparison_other_vendor")

        self.product_category = Category.objects.create(
            name="Comparison Merchandise",
            kind=Category.Kind.MERCHANDISE,
        )
        self.service_category = Category.objects.create(
            name="Comparison Services",
            kind=Category.Kind.SERVICES,
        )
        self.product_business = self.make_business(
            self.vendor,
            "Comparison Product Shop",
            Business.BusinessType.PRODUCT_SELLER,
            "comparison-product@example.com",
        )
        self.other_product_business = self.make_business(
            self.other_vendor,
            "Other Product Shop",
            Business.BusinessType.PRODUCT_SELLER,
            "other-product@example.com",
            city_district="Entebbe",
        )
        self.service_business = self.make_business(
            self.vendor,
            "Comparison Service Shop",
            Business.BusinessType.SERVICE_PROVIDER,
            "comparison-service@example.com",
        )
        self.pet_business = self.make_business(
            self.vendor,
            "Comparison Pet Shop",
            Business.BusinessType.PET_SALE_ADOPTION,
            "comparison-pet@example.com",
        )
        self.other_pet_business = self.make_business(
            self.other_vendor,
            "Other Pet Shop",
            Business.BusinessType.PET_SALE_ADOPTION,
            "other-pet@example.com",
            city_district="Entebbe",
        )

    def make_vendor(self, username):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="test-password",
            role=User.Role.VENDOR,
        )

    def make_business(
        self,
        vendor,
        name,
        business_type,
        email,
        city_district="Kampala",
    ):
        return Business.objects.create(
            vendor=vendor,
            name=name,
            description=f"{name} description",
            contact="+256700000001",
            email=email,
            address="Main Street",
            city_district=city_district,
            business_type=business_type,
            verification_status=Business.VerificationStatus.APPROVED,
        )

    def make_product(self, business=None, **overrides):
        values = {
            "business": business or self.product_business,
            "category": self.product_category,
            "name": "Comparison Toy",
            "description": "A durable toy",
            "price": "25.00",
            "stock_quantity": 4,
            "approved": True,
        }
        values.update(overrides)
        return Product.objects.create(**values)

    def make_service(self, **overrides):
        values = {
            "business": self.service_business,
            "category": self.service_category,
            "name": "Comparison Grooming",
            "service_type": "Grooming",
            "description": "Bath and trim",
            "price": "30000.00",
            "duration": 60,
            "approved": True,
        }
        values.update(overrides)
        return Service.objects.create(**values)

    def make_pet(self, business=None, **overrides):
        values = {
            "vendor": (business or self.pet_business).vendor,
            "business": business or self.pet_business,
            "listing_type": Pet.ListingType.ADOPTION,
            "name": "Comparison Pet",
            "species": "Dog",
            "breed": "Mixed",
            "age": 12,
            "gender": Pet.Gender.FEMALE,
            "size": Pet.Size.MEDIUM,
            "description": "Friendly and playful",
            "approved": True,
            "adoption_status": Pet.AdoptionStatus.AVAILABLE,
        }
        values.update(overrides)
        return Pet.objects.create(**values)

    def compare(self, listing_type, *listing_ids):
        return self.client.post(
            self.url,
            {"listing_type": listing_type, "listing_ids": list(listing_ids)},
            format="json",
        )

    def test_product_comparison_allows_different_vendors_and_returns_details(self):
        first = self.make_product()
        second = self.make_product(
            business=self.other_product_business,
            name="Other Toy",
            stock_quantity=0,
        )
        third = self.make_product(name="Third Toy")

        response = self.compare("product", second.pk, first.pk, third.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["listing_type"], "product")
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [second.pk, first.pk, third.pk],
        )
        self.assertEqual(response.data["results"][0]["description"], "A durable toy")
        self.assertFalse(response.data["results"][0]["is_available"])
        self.assertEqual(response.data["results"][0]["business_name"], "Other Product Shop")
        self.assertEqual(response.data["results"][0]["images"], [])
        self.assertIn("average_rating", response.data["results"][0])
        self.assertIn("review_count", response.data["results"][0])

    def test_service_comparison_returns_service_specific_details(self):
        first = self.make_service()
        second = self.make_service(name="Other Grooming", availability_status="unavailable")

        response = self.compare("service", first.pk, second.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["service_id"] for item in response.data["results"]],
            [first.pk, second.pk],
        )
        self.assertEqual(response.data["results"][0]["service_type"], "Grooming")
        self.assertEqual(response.data["results"][0]["duration"], 60)
        self.assertEqual(response.data["results"][1]["availability_status"], "unavailable")
        self.assertEqual(response.data["results"][0]["city_district"], "Kampala")

    def test_pet_comparison_returns_purpose_and_business_location(self):
        first = self.make_pet()
        second = self.make_pet(business=self.other_pet_business, name="Other Pet")

        response = self.compare("pet", first.pk, second.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["pet_id"] for item in response.data["results"]],
            [first.pk, second.pk],
        )
        self.assertEqual(response.data["results"][0]["listing_type"], "ADOPTION")
        self.assertEqual(response.data["results"][0]["city_district"], "Kampala")
        self.assertEqual(response.data["results"][1]["city_district"], "Entebbe")

    def test_sale_and_adoption_pets_cannot_be_compared_together(self):
        adoption = self.make_pet()
        sale = self.make_pet(
            name="Pet for Sale",
            listing_type=Pet.ListingType.SALE,
            price="500000.00",
        )

        response = self.compare("pet", adoption.pk, sale.pk)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("listing_ids", response.data)

    def test_missing_or_ineligible_listing_rejects_the_whole_comparison(self):
        visible = self.make_product()
        hidden = self.make_product(name="Pending Toy", approved=False)

        response = self.compare("product", visible.pk, hidden.pk)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("listing_ids", response.data)
        self.assertEqual(Product.objects.count(), 2)

    def test_missing_listing_returns_a_clear_error(self):
        visible = self.make_product()

        response = self.compare("product", visible.pk, visible.pk + 1000000)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("listing_ids", response.data)
        self.assertIn("not publicly available", str(response.data["listing_ids"]))

    def test_request_rejects_invalid_count_duplicate_ids_and_listing_type(self):
        product = self.make_product()

        with self.subTest(case="too few"):
            response = self.compare("product", product.pk)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        with self.subTest(case="duplicate"):
            response = self.compare("product", product.pk, product.pk)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("listing_ids", response.data)

        with self.subTest(case="too many"):
            response = self.compare("product", product.pk, 10001, 10002, 10003)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        with self.subTest(case="invalid category"):
            response = self.compare("product,service", product.pk, 2)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("listing_type", response.data)
