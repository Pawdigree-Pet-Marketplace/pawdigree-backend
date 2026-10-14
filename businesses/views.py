from rest_framework import generics

from common.permissions import IsVendor

from .models import Business
from .serializers import BusinessSerializer


class BusinessListCreateView(generics.ListCreateAPIView):
    serializer_class = BusinessSerializer
    permission_classes = (IsVendor,)

    def get_queryset(self):
        return Business.objects.filter(vendor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(vendor=self.request.user)


class BusinessDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = BusinessSerializer
    permission_classes = (IsVendor,)

    def get_queryset(self):
        return Business.objects.filter(vendor=self.request.user)
