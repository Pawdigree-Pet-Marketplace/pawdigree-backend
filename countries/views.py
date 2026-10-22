import unicodedata
from functools import lru_cache

import phonenumbers
import pycountry
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import CountryCodeSerializer


def sort_key(name):
    """Sort names ignoring accents and case, so 'Åland' sorts under A."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


@lru_cache(maxsize=1)
def get_country_codes():
    data = []
    for region in phonenumbers.SUPPORTED_REGIONS:
        country = pycountry.countries.get(alpha_2=region)
        if not country:
            continue
        data.append({
            "country": getattr(country, "common_name", country.name),
            "iso_code": region,
            "dial_code": f"+{phonenumbers.country_code_for_region(region)}",
        })
    data.sort(key=lambda c: sort_key(c["country"]))
    return tuple(data)


@extend_schema(
    responses=CountryCodeSerializer(many=True),
)
class CountryCodeListView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response(list(get_country_codes()))