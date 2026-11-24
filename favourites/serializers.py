from rest_framework import serializers


class FavouriteStatusSerializer(serializers.Serializer):
    pet = serializers.IntegerField()
    favourite = serializers.BooleanField()
    
class ProductFavouriteStatusSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    favourite = serializers.BooleanField()