from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from pets.views import public_pet_queryset
from products.views import public_products
from services.views import public_services

from .serializers import COMPARISON_SERIALIZERS, ComparisonRequestSerializer


PUBLIC_QUERYSETS = {
    "product": public_products,
    "service": public_services,
    "pet": public_pet_queryset,
}


class ListingComparisonView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    serializer_class = ComparisonRequestSerializer

    def post(self, request):
        request_serializer = self.serializer_class(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        listing_type = request_serializer.validated_data["listing_type"]
        listing_ids = request_serializer.validated_data["listing_ids"]

        queryset = PUBLIC_QUERYSETS[listing_type]()
        listings_by_id = {
            listing.pk: listing
            for listing in queryset.filter(pk__in=listing_ids)
        }
        unavailable_ids = [
            listing_id for listing_id in listing_ids if listing_id not in listings_by_id
        ]
        if unavailable_ids:
            raise ValidationError(
                {
                    "listing_ids": (
                        "These listings are missing or not publicly available: "
                        f"{unavailable_ids}."
                    )
                }
            )

        listings = [listings_by_id[listing_id] for listing_id in listing_ids]
        if listing_type == "pet" and len(
            {listing.listing_type for listing in listings}
        ) != 1:
            raise ValidationError(
                {"listing_ids": "Sale and adoption pets cannot be compared together."}
            )

        comparison_serializer = COMPARISON_SERIALIZERS[listing_type]
        results = comparison_serializer(
            listings,
            many=True,
            context={"request": request},
        ).data
        return Response({"listing_type": listing_type, "results": results})
