from functools import lru_cache

import phonenumbers
import pycountry
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


@lru_cache(maxsize=1)
def get_country_codes():
    data = []
    for region in phonenumbers.SUPPORTED_REGIONS:
        country = pycountry.countries.get(alpha_2=region)
        if not country:
            continue
        data.append({
            "country": country.name,
            "iso_code": region,
            "dial_code": f"+{phonenumbers.country_code_for_region(region)}",
        })
    data.sort(key=lambda c: c["country"])
    return tuple(data)


class CountryCodeListView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response(list(get_country_codes()))