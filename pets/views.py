
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record as record_audit
from businesses.models import Business
from common.bulk_csv import csv_template_response, read_bulk_csv
from common.permissions import IsAdmin, IsVendor

from .filters import (
    SORT_OPTIONS,
    filter_admin_pets,
    filter_public_pets,
    public_locations,
)
from .models import Pet, PetImage
from .notifications import notify_listing_approved, notify_listing_rejected
from .serializers import (
    AdminPetUpdateSerializer,
    PetImageEditSerializer,
    PetRejectSerializer,
    PetSerializer,
    PublicPetSerializer,
)

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

# Delete a pet listing. 
# This is separate from the list/create view so that permissions and serializers can be different.
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
    page_size_query_param = "page_size"
    max_page_size = 50


def public_pet_queryset():
    return (
        Pet.objects.publicly_visible()
        .select_related("business")
        .prefetch_related("images")
    )


# Public views for browsing listings.
# These are separate from the vendor and admin views, so that permissions and serializers can be different.
@extend_schema(
    tags=["pets"],
    summary="Browse pet listings",
    description=(
        "Public list of approved, active pet listings. Open to everyone, "
        "logged in or not. Deactivated and unapproved listings are never "
        "included, whatever filters are used. Pets with no price (adoption "
        "listings) are left out whenever a price filter is used."
    ),
    parameters=[
        OpenApiParameter(
            "search",
            str,
            description="Matches name, breed, species or description.",
        ),
        OpenApiParameter("breed", str, description="Exact breed, any case."),
        OpenApiParameter(
            "species",
            str,
            description="Species, any case. Repeat it or use commas: species=dog,cat.",
        ),
        OpenApiParameter(
            "vendor",
            str,
            description="Part of the business name, any case.",
        ),
        OpenApiParameter(
            "location",
            str,
            description="Town or district, any case. Repeat it or use commas.",
        ),
        OpenApiParameter("gender", str, enum=Pet.Gender.values),
        OpenApiParameter("listing_type", str, enum=Pet.ListingType.values),
        OpenApiParameter("age_min", int, description="Minimum age in months."),
        OpenApiParameter("age_max", int, description="Maximum age in months."),
        OpenApiParameter("price_min", float, description="Minimum price."),
        OpenApiParameter("price_max", float, description="Maximum price."),
        OpenApiParameter(
            "sort",
            str,
            enum=list(SORT_OPTIONS),
            description="popular means applied for by the most customers.",
        ),
        OpenApiParameter(
            "page_size", int, description="Results per page (default 20, max 50)."
        ),
    ],
)
class PublicPetListView(generics.ListAPIView):
    serializer_class = PublicPetSerializer
    permission_classes = (AllowAny,)
    # Ignore any token, so an expired one can't turn a public page into a 401.
    authentication_classes = ()
    pagination_class = PublicPetPagination

    def get_queryset(self):
        return filter_public_pets(
            public_pet_queryset(), self.request.query_params
        )


@extend_schema(
    tags=["pets"],
    summary="View one pet listing",
    description=(
        "Public detail of one approved, active pet listing. Open to "
        "everyone. Deactivated and unapproved listings return 404."
    ),
)
class PublicPetDetailView(generics.RetrieveAPIView):
    serializer_class = PublicPetSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get_queryset(self):
        return public_pet_queryset()


@extend_schema(
    tags=["pets"],
    summary="Towns that have pet listings",
    description="Sorted list of towns for the location filter and its suggestions.",
    responses={200: {"type": "array", "items": {"type": "string"}}},
)
class PublicPetLocationListView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request):
        return Response(public_locations())

@extend_schema_view(
    get=extend_schema(
        tags=["pets"],
        summary="View any pet listing (administrators)",
        description="Any listing, approved or not, active or deactivated.",
    ),
    put=extend_schema(
        tags=["pets"],
        summary="Edit any pet listing (administrators)",
        description=(
            "Corrects a listing's details even after approval. The listing "
            "keeps its business, owner, approval status and active state, "
            "and photos are not changed here."
        ),
    ),
    patch=extend_schema(
        tags=["pets"],
        summary="Edit any pet listing (administrators)",
        description=(
            "Corrects a listing's details even after approval. The listing "
            "keeps its business, owner, approval status and active state, "
            "and photos are not changed here."
        ),
    ),
    delete=extend_schema(
        tags=["pets"],
        summary="Remove a pet listing (administrators)",
        description=(
            "Deactivates the listing so customers no longer see it. "
            "Nothing is deleted from the database."
        ),
    ),
)
class AdminPetDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAdmin,)

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return AdminPetUpdateSerializer
        return PetSerializer

    def get_queryset(self):
        queryset = Pet.objects.select_related(
            "business", "vendor"
        ).prefetch_related("images")
        if self.request.method == "DELETE":
            # Removing an already removed listing stays a 404.
            return queryset.filter(is_active=True)
        return queryset

    def perform_update(self, serializer):
        # Field names only, never values, so the log holds no personal data.
        changed = sorted(
            name
            for name, value in serializer.validated_data.items()
            if getattr(serializer.instance, name, None) != value
        )
        with transaction.atomic():
            pet = serializer.save()
            record_audit(
                actor=self.request.user,
                action="pet.admin_updated",
                target=pet,
                details={"fields": changed},
            )

    def perform_destroy(self, instance):
        with transaction.atomic():
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
            record_audit(
                actor=self.request.user,
                action="pet.admin_removed",
                target=instance,
                details={"business": str(instance.business_id)},
            )


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



#Admin views for reviewing listings. These are separate from the public and vendor views, so that permissions and serializers can be different.
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


@extend_schema(
    tags=["pets"],
    summary="List every pet listing (administrators)",
    description=(
        "Every listing on the platform, approved or not, active or "
        "deactivated, newest first. Use it to find listings that break "
        "platform rules, even after approval."
    ),
    parameters=[
        OpenApiParameter(
            "search", str,
            description="Matches name, breed, species, description or business name.",
        ),
        OpenApiParameter("species", str, description="One or more, comma separated."),
        OpenApiParameter("listing_type", str, description="ADOPTION or SALE."),
        OpenApiParameter(
            "adoption_status", str, description="AVAILABLE, PENDING or ADOPTED."
        ),
        OpenApiParameter(
            "review_status", str, description="APPROVED, PENDING or REJECTED."
        ),
        OpenApiParameter(
            "is_active", bool, description="false shows only deactivated listings."
        ),
        OpenApiParameter("business", str, description="Business id."),
    ],
)
class AdminPetListView(generics.ListAPIView):
    serializer_class = PetSerializer
    permission_classes = (IsAdmin,)
    pagination_class = PublicPetPagination

    def get_queryset(self):
        queryset = (
            Pet.objects.all()
            .select_related("business", "vendor")
            .prefetch_related("images")
        )
        return filter_admin_pets(queryset, self.request.query_params)

    
class AdminPetReviewBaseView(generics.GenericAPIView):
    serializer_class = PetSerializer
    permission_classes = (IsAdmin,)

    def get_queryset(self):
        return (
            Pet.objects.filter(is_active=True)
            .select_related("business", "vendor")
            .prefetch_related("images")
        )

#Admin views for approving or rejecting listings. These are separate from the public and vendor views, so that permissions and serializers can be different.
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

        record_audit(
            actor=request.user,
            action="pet.approved",
            target=pet,
            details={"business": str(pet.business_id)},
        )

        # Notify only if the database change actually committed.
        transaction.on_commit(lambda: notify_listing_approved(pet))

        return Response(self.get_serializer(pet).data)

#Admin views for approving or rejecting listings. These are separate from the public and vendor views, so that permissions and serializers can be different.
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

        # The reason itself stays on the listing; the log only notes the action.
        record_audit(
            actor=request.user,
            action="pet.rejected",
            target=pet,
            details={"business": str(pet.business_id)},
        )

        transaction.on_commit(lambda: notify_listing_rejected(pet))

        return Response(self.get_serializer(pet).data)

BULK_COLUMNS = (
    "business_id",
    "listing_type",
    "name",
    "species",
    "breed",
    "age",
    "gender",
    "size",
    "description",
    "price",
)
BULK_REQUIRED_COLUMNS = ("listing_type", "name", "species", "age", "gender", "size")


@extend_schema(
    tags=["pets"],
    summary="Bulk upload pet listings (vendors)",
    description=(
        "Upload a CSV file to create many listings at once. Every row is "
        "validated with the same rules as a single listing. Valid rows are "
        "created and sent for admin review; invalid rows are returned with "
        "the row number and the errors. business_id can be left blank if "
        "the vendor owns only one business."
    ),
    request={
        "multipart/form-data": {
            "type": "object",
            "properties": {"file": {"type": "string", "format": "binary"}},
            "required": ["file"],
        }
    },
    responses={
        200: inline_serializer(
            name="PetBulkUploadResult",
            fields={
                "created": serializers.IntegerField(),
                "failed": serializers.ListField(child=serializers.DictField()),
            },
        ),
        400: OpenApiResponse(
            description="Whole-file problem (see the 'file' error message)."
        ),
    },
)
class PetBulkUploadView(APIView):
    permission_classes = (IsVendor,)
    parser_classes = (MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request):
        rows = read_bulk_csv(
            request.FILES.get("file"),
            BULK_COLUMNS,
            BULK_REQUIRED_COLUMNS,
        )

        # A vendor with exactly one approved, active business doesn't need
        # to fill business_id.
        owned = list(
            Business.objects.filter(
                vendor=request.user,
                is_active=True,
                verification_status=Business.VerificationStatus.APPROVED,
                business_type=Business.BusinessType.PET_SALE_ADOPTION,
            )
        )
        default_business = owned[0] if len(owned) == 1 else None

        valid_serializers = []
        failed = []

        for row_number, data in rows:
            for field in ("listing_type", "gender", "size"):
                if field in data:
                    data[field] = data[field].upper()

            if "business_id" in data:
                data["business"] = data.pop("business_id")
            elif default_business:
                data["business"] = default_business.pk

            serializer = PetSerializer(data=data, context={"request": request})

            if serializer.is_valid():
                valid_serializers.append(serializer)
            else:
                failed.append({"row": row_number, "errors": serializer.errors})

        for serializer in valid_serializers:
            serializer.save(vendor=request.user)

        return Response({"created": len(valid_serializers), "failed": failed})

@extend_schema(
    tags=["pets"],
    summary="Download the bulk upload CSV template",
    description="Public CSV template with the required columns and two example rows.",
    responses={(200, "text/csv"): OpenApiTypes.STR},
)
class PetBulkTemplateView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request):
        return csv_template_response(
            BULK_COLUMNS,
            [
                ",SALE,Buddy,Dog,Labrador,12,MALE,MEDIUM,Friendly and vaccinated,450000",
                ",ADOPTION,Mimi,Cat,,6,FEMALE,SMALL,Needs a loving home,",
            ],
            "pet_listings_template.csv",
        )


