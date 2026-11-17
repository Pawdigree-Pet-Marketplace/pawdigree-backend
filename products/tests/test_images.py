import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from businesses.models import Business
from categories.models import Category
from products.models import Product, ProductImage

TEST_MEDIA_ROOT = tempfile.mkdtemp()


def make_image(name="toy.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "teal").save(buffer, format="PNG")
    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        content_type="image/png",
    )


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ProductImageTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user(
            username="image_vendor",
            email="image-vendor@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.other_vendor = User.objects.create_user(
            username="other_image_vendor",
            email="other-image-vendor@example.com",
            password="test-password-123",
            role=User.Role.VENDOR,
        )
        cls.customer = User.objects.create_user(
            username="image_customer",
            email="image-customer@example.com",
            password="test-password-123",
            role=User.Role.CUSTOMER,
        )
        cls.admin = User.objects.create_user(
            username="image_admin",
            email="image-admin@example.com",
            password="test-password-123",
            role=User.Role.ADMIN,
        )
        cls.category = Category.objects.create(kind=Category.Kind.MERCHANDISE, name="Pet Toys")
        cls.business = Business.objects.create(
            vendor=cls.vendor,
            name="Image Shop",
            description="Toys",
            verification_status=Business.VerificationStatus.APPROVED,
        )
        cls.product = Product.objects.create(
            business=cls.business,
            category=cls.category,
            name="Chew Toy",
            price="15.00",
            stock_quantity=5,
            approved=True,
        )

    def create_url(self, product=None):
        product = product or self.product
        return reverse("product-image-create", kwargs={"product_pk": product.pk})

    def delete_url(self, image, product=None):
        product = product or self.product
        return reverse(
            "product-image-delete",
            kwargs={"product_pk": product.pk, "pk": image.pk},
        )

    def upload(self, **extra):
        data = {"image": make_image(), "alt_text": "A chew toy"}
        data.update(extra)
        return self.client.post(self.create_url(), data, format="multipart")

    def test_vendor_can_add_image_to_own_product(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["alt_text"], "A chew toy")
        self.assertEqual(self.product.images.count(), 1)

    def test_admin_can_add_image_to_any_product(self):
        self.client.force_authenticate(user=self.admin)

        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.product.images.count(), 1)

    def test_vendor_adding_an_image_sends_the_product_back_for_review(self):
        self.client.force_authenticate(user=self.vendor)

        self.upload()

        self.product.refresh_from_db()
        self.assertFalse(self.product.approved)

    def test_admin_adding_an_image_keeps_the_approval(self):
        self.client.force_authenticate(user=self.admin)

        self.upload()

        self.product.refresh_from_db()
        self.assertTrue(self.product.approved)

    def test_uploaded_image_becomes_the_main_image_on_public_list(self):
        self.client.force_authenticate(user=self.vendor)
        self.upload()
        # A vendor upload sends the product back to review, so approve it
        # again the way an admin would before checking the public list.
        Product.objects.filter(pk=self.product.pk).update(approved=True)
        self.client.force_authenticate(user=None)

        response = self.client.get(reverse("product-public-list"))

        self.assertIsNotNone(response.data["results"][0]["main_image"])

    def test_vendor_cannot_add_image_to_another_vendors_product(self):
        self.client.force_authenticate(user=self.other_vendor)

        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.product.images.count(), 0)

    def test_customer_cannot_add_image(self):
        self.client.force_authenticate(user=self.customer)

        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.product.images.count(), 0)

    def test_anonymous_user_cannot_add_image(self):
        response = self.upload()

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        self.assertEqual(self.product.images.count(), 0)

    def test_file_that_is_not_an_image_is_rejected(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.upload(
            image=SimpleUploadedFile(
                "notes.txt",
                b"not an image",
                content_type="text/plain",
            )
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", response.data)
        self.assertEqual(self.product.images.count(), 0)

    def test_product_cannot_have_more_than_five_images(self):
        for number in range(5):
            ProductImage.objects.create(
                product=self.product,
                image=f"products/test-{number}.png",
            )
        self.client.force_authenticate(user=self.vendor)

        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", response.data)
        self.assertEqual(self.product.images.count(), 5)

    def test_vendor_can_delete_own_product_image(self):
        image = ProductImage.objects.create(
            product=self.product,
            image="products/test.png",
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.delete(self.delete_url(image))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ProductImage.objects.filter(pk=image.pk).exists())

    def test_vendor_cannot_delete_another_vendors_image(self):
        image = ProductImage.objects.create(
            product=self.product,
            image="products/test.png",
        )
        self.client.force_authenticate(user=self.other_vendor)

        response = self.client.delete(self.delete_url(image))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(ProductImage.objects.filter(pk=image.pk).exists())

    def test_customer_cannot_delete_image(self):
        image = ProductImage.objects.create(
            product=self.product,
            image="products/test.png",
        )
        self.client.force_authenticate(user=self.customer)

        response = self.client.delete(self.delete_url(image))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ProductImage.objects.filter(pk=image.pk).exists())