from rest_framework import serializers


class CountryCodeSerializer(serializers.Serializer):
    country = serializers.CharField()
    iso_code = serializers.CharField()
    dial_code = serializers.CharField()
