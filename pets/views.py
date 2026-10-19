from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.permissions import IsAdmin, IsVendor

from .models import Pet, PetImage
from .serializers import PetSerializer, PublicPetSerializer, PetImageEditSerializer

MAX_IMAGES_PER_LISTING = 10


@extend_schema(
    tags=["pets"],
    summary="List or create pet listings",
    description=(
        "Allows authenticated vendors to view their own pet listings "
        "and create new listings for businesses they own."
    ),
)
class PetListCreateView(generics.ListCreateAPIView):
    serializer_class = PetSerializer
    permission_classes = (IsVendor,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        return (
            Pet.objects.filter(vendor=self.request.user)
            .select_related("business", "vendor")
            .prefetch_related("images")
        )

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        uploaded_images = request.FILES.getlist("images")

        if len(uploaded_images) > MAX_IMAGES_PER_LISTING:
            raise serializers.ValidationError({
                "images": (
                    f"You can upload at most {MAX_IMAGES_PER_LISTING} images."
                )
            })

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Validate every file before anything is saved, so a bad image
        # leaves no pet row and no orphaned file behind.
        image_field = PetImage._meta.get_field("image")
        for uploaded_image in uploaded_images:
            try:
                image_field.run_validators(uploaded_image)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(
                    {"images": exc.messages}
                ) from exc

        pet = serializer.save(vendor=request.user)

        for position, uploaded_image in enumerate(uploaded_images):
            PetImage.objects.create(
                pet=pet,
                image=uploaded_image,
                is_primary=(position == 0),
                position=position,
            )

        headers = self.get_success_headers(serializer.data)
        response_serializer = self.get_serializer(pet)

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


@extend_schema(
    tags=["pets"],
    summary="Deactivate a pet listing",
    description=(
        "Soft-deletes one of the authenticated vendor's own listings. "
        "The row is kept with is_active set to false."
    ),
)
class PetDetailView(generics.DestroyAPIView):
    serializer_class = PetSerializer
    permission_classes = (IsVendor,)

    def get_queryset(self):
        # Scoping to the vendor's own active pets means another vendor's
        # pet, or an already deactivated one, returns 404.
        return Pet.objects.filter(vendor=self.request.user, is_active=True)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class PublicPetPagination(PageNumberPagination):
    page_size = 20


@extend_schema(
    tags=["pets"],
    summary="Browse pet listings",
    description=(
        "Public list of approved, active pet listings. Open to everyone, "
        "logged in or not. Deactivated and unapproved listings are never "
        "included."
    ),
)
class PublicPetListView(generics.ListAPIView):
    serializer_class = PublicPetSerializer
    permission_classes = (AllowAny,)
    # Ignore any token, so an expired one can't turn a public page into a 401.
    authentication_classes = ()
    pagination_class = PublicPetPagination

    def get_queryset(self):
        return (
            Pet.objects.publicly_visible()
            .select_related("business")
            .prefetch_related("images")
        )


@extend_schema(
    tags=["pets"],
    summary="Deactivate any pet listing (administrators)",
    description=(
        "Lets an admin or system admin deactivate any vendor's active "
        "listing. The row is kept with is_active set to false."
    ),
)
class AdminPetDeactivateView(generics.DestroyAPIView):
    serializer_class = PetSerializer
    permission_classes = (IsAdmin,)

    def get_queryset(self):
        return Pet.objects.filter(is_active=True)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
