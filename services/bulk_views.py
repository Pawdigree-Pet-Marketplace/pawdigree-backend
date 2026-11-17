from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from businesses.models import Business
from common.bulk_csv import csv_template_response, read_bulk_csv
from common.permissions import IsVendor

from .serializers import ServiceSerializer

BULK_COLUMNS = (
    "business_id",
    "category_id",
    "name",
    "service_type",
    "description",
    "price",
    "duration",
    "availability_status",
)
BULK_REQUIRED_COLUMNS = (
    "category_id",
    "name",
    "service_type",
    "description",
    "price",
    "duration",
)


def get_default_business(vendor):
    """The vendor's only approved, active Pet Services business, if exactly one."""
    eligible = list(
        Business.objects.filter(
            vendor=vendor,
            is_active=True,
            verification_status=Business.VerificationStatus.APPROVED,
            business_type=Business.BusinessType.SERVICE_PROVIDER,
        )[:2]
    )
    return eligible[0] if len(eligible) == 1 else None


@extend_schema(
    tags=["services"],
    summary="Bulk upload services (vendors)",
    description=(
        "Upload a CSV file to create many services at once. Every row is "
        "validated with the same rules as a single service. Valid rows are "
        "created as unapproved services and stay hidden from customers "
        "until an administrator approves them; invalid rows are returned "
        "with the row number and the errors. A category the business has "
        "not used before is requested as pending, and those services also "
        "stay hidden until the category is approved. business_id can be "
        "left blank if the "
        "vendor owns exactly one approved Pet Services business."
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
            name="ServiceBulkUploadResult",
            fields={
                "created": serializers.IntegerField(),
                "created_ids": serializers.ListField(
                    child=serializers.IntegerField()
                ),
                "failed": serializers.ListField(child=serializers.DictField()),
            },
        ),
        400: OpenApiResponse(
            description="Whole-file problem (see the 'file' error message)."
        ),
    },
)
class ServiceBulkUploadView(APIView):
    permission_classes = (IsAuthenticated, IsVendor)
    parser_classes = (MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request):
        rows = read_bulk_csv(
            request.FILES.get("file"),
            BULK_COLUMNS,
            BULK_REQUIRED_COLUMNS,
        )
        default_business = get_default_business(request.user)

        valid_serializers = []
        failed = []

        for row_number, data in rows:
            if "business_id" in data:
                data["business"] = data.pop("business_id")
            elif default_business:
                data["business"] = default_business.pk

            if "category_id" in data:
                data["category"] = data.pop("category_id")

            serializer = ServiceSerializer(
                data=data, context={"request": request}
            )

            if serializer.is_valid():
                valid_serializers.append(serializer)
            else:
                failed.append({"row": row_number, "errors": serializer.errors})

        created_ids = []
        for serializer in valid_serializers:
            serializer.save()
            created_ids.append(serializer.instance.pk)

        return Response(
            {
                "created": len(valid_serializers),
                "created_ids": created_ids,
                "failed": failed,
            }
        )


@extend_schema(
    tags=["services"],
    summary="Download the services bulk upload CSV template",
    description=(
        "Public CSV template with the required columns and two example "
        "rows. category_id values must come from GET /api/categories/, "
        "using an active services category."
    ),
    responses={(200, "text/csv"): OpenApiTypes.STR},
)
class ServiceBulkTemplateView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request):
        return csv_template_response(
            BULK_COLUMNS,
            [
                ",1,Dog Grooming,Grooming,Bath and trim for dogs,30000,60,available",
                ",1,Vet Check-up,Health,General health check,50000,30,available",
            ],
            "service_bulk_upload_template.csv",
        )
