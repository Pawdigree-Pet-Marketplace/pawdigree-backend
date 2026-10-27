from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from businesses.models import Business

Status = Business.VerificationStatus

class StatusMoveTests(TestCase):
    def setUp(self):
        # Two vendors and an admin, to test ownership and roles.
        self.admin = User.objects.create_user(
            username="admin1", email="admin@example.com",
            password="Test12345!", role=User.Role.ADMIN,
        )
        self.vendor = User.objects.create_user(
            username="vendor1", email="vendor@example.com",
            password="Test12345!", role=User.Role.VENDOR,
        )
        self.other = User.objects.create_user(
            username="vendor2", email="vendor2@example.com",
            password="Test12345!", role=User.Role.VENDOR,
        )
        self.business = Business.objects.create(
            vendor=self.vendor, name="Paws Place", description="Pets",
            contact="0700000000", email="shop@example.com",
            address="1 Main St", city_district="Kampala",
            verification_status=Status.PENDING,
        )
        # Requests are made as the business owner unless a test says otherwise.
        self.client = APIClient()
        self.client.force_authenticate(self.vendor)
        
    def set_status(self, value):
        """Put business in a given status before a test."""
        self.business.verification_status = value
        self.business.save()
        
    def current_status(self):
        """Read the current status from the database."""
        self.business.refresh_from_db()
        return self.business.verification_status
    
    def post(self, route, body=None):
        """POST to one of the status-move routes for this business."""
        url = reverse(route, kwargs={"pk": self.business.pk})
        return self.client.post(url, body or {}, format="json")