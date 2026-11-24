from django.conf import settings
from django.test import TestCase
from django.urls import reverse


class CartTokenCorsTests(TestCase):
    def test_preflight_allows_the_cart_token_header(self):
        origin = settings.CORS_ALLOWED_ORIGINS[0]

        response = self.client.options(
            reverse("cart"),
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-cart-token",
        )

        self.assertEqual(response.status_code, 200)
        allowed = response["Access-Control-Allow-Headers"].lower()
        self.assertIn("x-cart-token", allowed)
        self.assertIn("authorization", allowed)
