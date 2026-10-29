from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsCustomer
from pets.serializers import PublicPetSerializer
from pets.views import PublicPetPagination

from .serializers import FavouriteStatusSerializer
from .services import (
    add_favourite,
    favourite_pet_ids,
    favourite_pets,
    remove_favourite,
)


@extend_schema(
    tags=["favourites"],
    summary="My favourite pets",
    description=(
        "The customer's saved pets, newest first, in the same shape as the "
        "public pet list. Pets that are no longer approved, active and "
        "available are left out."
    ),
)
class FavouriteListView(generics.ListAPIView):
    serializer_class = PublicPetSerializer
    permission_classes = (IsAuthenticated, IsCustomer)
    pagination_class = PublicPetPagination

    def get_queryset(self):
        return favourite_pets(self.request.user)


@extend_schema(
    tags=["favourites"],
    summary="Ids of my favourite pets",
    description="Used to fill the heart on pet cards.",
    responses={200: {"type": "array", "items": {"type": "integer"}}},
)
class FavouriteIdsView(APIView):
    permission_classes = (IsAuthenticated, IsCustomer)

    def get(self, request):
        return Response(favourite_pet_ids(request.user))


@extend_schema_view(
    put=extend_schema(
        tags=["favourites"],
        summary="Add a pet to my favourites",
        description=(
            "Saving the same pet twice is harmless: 201 the first time, "
            "200 if it was already saved."
        ),
        request=None,
        responses={200: FavouriteStatusSerializer, 201: FavouriteStatusSerializer},
    ),
    delete=extend_schema(
        tags=["favourites"],
        summary="Remove a pet from my favourites",
        description="Always 204, even if the pet was not saved.",
        responses={204: None},
    ),
)
class FavouriteDetailView(generics.GenericAPIView):
    serializer_class = FavouriteStatusSerializer
    permission_classes = (IsAuthenticated, IsCustomer)

    def put(self, request, pet_id):
        _, created = add_favourite(request.user, pet_id)
        return Response(
            {"pet": pet_id, "favourite": True},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, pet_id):
        remove_favourite(request.user, pet_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
