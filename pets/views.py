from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.utils import timezone

from common.permissions import IsAdmin, IsVendor

from .models import Pet, PetImage
from .notifications import notify_listing_approved, notify_listing_rejected
from .serializers import PetSerializer, PublicPetSerializer, PetImageEditSerializer, PetRejectSerializer

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
        
        
@extend_schema(
    tags=["pets"],
    summary="Edit a pet listing",
    description=(
        "Lets a vendor edit one of their own active listings, including "
        "its photos. Send new files in 'images', ids to delete in "
        "'remove_image_ids' and the id of the main photo in "
        "'primary_image_id'. Every edit sets approved back to false so the "
        "listing is reviewed again."
    ),
)
class PetUpdateView(generics.UpdateAPIView):
    serializer_class = PetSerializer
    permission_classes = (IsVendor,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        # Another vendor's pet, or a deactivated one, returns 404.
        return (
            Pet.objects.filter(vendor=self.request.user, is_active=True)
            .select_related("business", "vendor")
            .prefetch_related("images")
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        pet = self.get_object()

        #To validate everything before changing anything.
        serializer = self.get_serializer(pet, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        edits = PetImageEditSerializer(data=request.data)
        edits.is_valid(raise_exception=True)
        remove_ids = set(edits.validated_data.get("remove_image_ids", []))
        primary_id = edits.validated_data.get("primary_image_id")
        new_files = request.FILES.getlist("images")

        current_images = list(pet.images.all())
        current_ids = {image.pk for image in current_images}

        if remove_ids - current_ids:
            raise serializers.ValidationError({
                "remove_image_ids": "Some ids are not images of this listing."
            })

        if primary_id is not None and (
            primary_id not in current_ids or primary_id in remove_ids
        ):
            raise serializers.ValidationError({
                "primary_image_id": (
                    "Must be an existing image of this listing that "
                    "is not being removed."
                )
            })

        total = len(current_images) - len(remove_ids) + len(new_files)
        if total > MAX_IMAGES_PER_LISTING:
            raise serializers.ValidationError({
                "images": (
                    f"A listing can have at most {MAX_IMAGES_PER_LISTING} "
                    f"images (this edit would leave {total})."
                )
            })

        image_field = PetImage._meta.get_field("image")
        for uploaded_image in new_files:
            try:
                image_field.run_validators(uploaded_image)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(
                    {"images": exc.messages}
                ) from exc

        #Save the listing. Any edit sends it back for review.
        pet = serializer.save(
            approved=False,            
            rejection_reason="",
            reviewed_by=None,
            reviewed_at=None,
        )

        #To remove images here, files are deleted only if the transaction commits.
        for image in current_images:
            if image.pk in remove_ids:
                storage, name = image.image.storage, image.image.name
                image.delete()
                transaction.on_commit(
                    lambda s=storage, n=name: s.delete(n)
                )

        #Add new images after the remaining ones.
        remaining = [i for i in current_images if i.pk not in remove_ids]
        next_position = max((i.position for i in remaining), default=-1) + 1
        for offset, uploaded_image in enumerate(new_files):
            PetImage.objects.create(
                pet=pet,
                image=uploaded_image,
                is_primary=False,
                position=next_position + offset,
            )

        #Keep exactly one primary image.
        images = pet.images.all()
        if primary_id is not None:
            images.update(is_primary=False)
            images.filter(pk=primary_id).update(is_primary=True)
        elif images.exists() and not images.filter(is_primary=True).exists():
            first = images.first()
            first.is_primary = True
            first.save(update_fields=["is_primary"])

        #Re-fetch so the response includes the new images.
        pet = (
            Pet.objects.select_related("business", "vendor")
            .prefetch_related("images")
            .get(pk=pet.pk)
        )
        return Response(self.get_serializer(pet).data)
    
    

#ADMIN REVIEW VIEWS--------------------------------------
@extend_schema(
    tags=["pets"],
    summary="List listings waiting for review (administrators)",
    description="Active listings that are neither approved nor rejected, oldest first.",
)
class AdminPendingPetListView(generics.ListAPIView):
    serializer_class = PetSerializer
    permission_classes = (IsAdmin,)
    pagination_class = PublicPetPagination

    def get_queryset(self):
        return (
            Pet.objects.pending_review()
            .select_related("business", "vendor")
            .prefetch_related("images")
            .order_by("created_at")
        )


class AdminPetReviewBaseView(generics.GenericAPIView):
    serializer_class = PetSerializer
    permission_classes = (IsAdmin,)

    def get_queryset(self):
        return (
            Pet.objects.filter(is_active=True)
            .select_related("business", "vendor")
            .prefetch_related("images")
        )


@extend_schema(
    tags=["pets"],
    summary="Approve a pet listing (administrators)",
    request=None,
    description="Makes the listing public and notifies the vendor.",
)
class AdminPetApproveView(AdminPetReviewBaseView):

    @transaction.atomic
    def post(self, request, pk):
        pet = self.get_object()

        if pet.approved:
            raise serializers.ValidationError("This listing is already approved.")

        pet.approved = True
        pet.rejection_reason = ""
        pet.reviewed_by = request.user
        pet.reviewed_at = timezone.now()
        pet.save(update_fields=[
            "approved", "rejection_reason", "reviewed_by",
            "reviewed_at", "updated_at",
        ])

        # Notify only if the database change actually committed.
        transaction.on_commit(lambda: notify_listing_approved(pet))

        return Response(self.get_serializer(pet).data)


@extend_schema(
    tags=["pets"],
    summary="Reject a pet listing (administrators)",
    request=PetRejectSerializer,
    description=(
        "Hides the listing, stores the reason and notifies the vendor. "
        "The vendor can edit the listing to send it for review again."
    ),
)
class AdminPetRejectView(AdminPetReviewBaseView):

    @transaction.atomic
    def post(self, request, pk):
        pet = self.get_object()

        if not pet.approved and pet.rejection_reason:
            raise serializers.ValidationError("This listing is already rejected.")

        data = PetRejectSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        pet.approved = False
        pet.rejection_reason = data.validated_data["reason"]
        pet.reviewed_by = request.user
        pet.reviewed_at = timezone.now()
        pet.save(update_fields=[
            "approved", "rejection_reason", "reviewed_by",
            "reviewed_at", "updated_at",
        ])

        transaction.on_commit(lambda: notify_listing_rejected(pet))

        return Response(self.get_serializer(pet).data)
