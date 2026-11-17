from django.test import TestCase

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from products.models import Product, ProductImage


class ProductModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="product_vendor",
            email="vendor@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.category = Category.objects.create(
                           kind=Category.Kind.MERCHANDISE,
            name="Pet Toys",
        )
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Happy Pets",
            description="Pet supplies and accessories",
            contact="+256700000001",
            email="business@example.com",
            address="Kampala",
            city_district="Central",
        )

    def test_product_creation_and_relationships(self):
        product = Product.objects.create(
            business=self.business,
            category=self.category,
            name="Rubber Ball",
            price="15000.00",
        )

        self.assertEqual(product.business, self.business)
        self.assertEqual(product.category, self.category)
        self.assertEqual(product.name, "Rubber Ball")
        self.assertEqual(str(product), "Rubber Ball")

    def test_product_defaults(self):
        product = Product.objects.create(
            business=self.business,
            category=self.category,
            name="Pet Brush",
            price="10000.00",
        )

        self.assertTrue(product.is_active)
        self.assertEqual(product.description, "")
        self.assertIsNotNone(product.created_at)
        self.assertIsNotNone(product.updated_at)

    def test_product_image_relationship_and_ordering(self):
        product = Product.objects.create(
            business=self.business,
            category=self.category,
            name="Chew Toy",
            price="12000.00",
        )

        later_image = ProductImage.objects.create(
            product=product,
            image="products/later.png",
            display_order=2,
        )
        earlier_image = ProductImage.objects.create(
            product=product,
            image="products/earlier.png",
            display_order=1,
        )

        self.assertEqual(product.images.count(), 2)
        self.assertEqual(
            list(product.images.all()),
            [earlier_image, later_image],
        )
        self.assertEqual(str(earlier_image), "Image for Chew Toy")
