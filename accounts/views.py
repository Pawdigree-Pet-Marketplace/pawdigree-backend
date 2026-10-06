from rest_framework import generics
from rest_framework.permissions import AllowAny

from .serializers import CustomerRegistrationSerializer, VendorRegistrationSerializer


class CustomerRegistrationView(generics.CreateAPIView):
    serializer_class = CustomerRegistrationSerializer
    permission_classes = [AllowAny]


class VendorRegistrationView(generics.CreateAPIView):
    serializer_class = VendorRegistrationSerializer
    permission_classes = [AllowAny]