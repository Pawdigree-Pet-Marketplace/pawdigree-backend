from rest_framework import serializers
from .models import MAX_QUANTITY_PER_ITEM

class CartLineSerializer(serializers.Serializer):
    """One cart line. Reads from a CartLine built by the service."""

    # source="item.id" follows  CartLine -> item -> id.
    id = serializers.IntegerField(source="item.id")
    product_id = serializers.IntegerField(source="item.product_id")
    name = serializers.CharField(source="item.product.name")
    business_name = serializers.CharField(source="item.product.business.name")
    image = serializers.SerializerMethodField()
    unit_price = serializers.DecimalField(source="item.product.price", max_digits=12, decimal_places=2)
    quantity = serializers.IntegerField(source="item.quantity")
    line_total = serializers.DecimalField(max_digits=16, decimal_places=2)
    available = serializers.BooleanField()
    issue = serializers.CharField(allow_null=True)
    max_quantity = serializers.IntegerField()
    
    
    def get_image(self, obj) -> str | None:
        # The images were prefetched.
        first = next(iter(obj.item.product.images.all()), None)
        if first is None:
            return None

        request = self.context.get("request")
        url = first.image.url
        return request.build_absolute_uri(url) if request else url
    

class CartSerializer(serializers.Serializer):
    """The whole cart. Reads from a CartSummary built by the service."""

    items = CartLineSerializer(source="lines", many=True)
    total_quantity = serializers.IntegerField()
    total = serializers.DecimalField(max_digits=16, decimal_places=2)
    has_unavailable_items = serializers.BooleanField()
    # The guest's secret token. Only set when a guest adds to a cart.
    cart_token = serializers.UUIDField(read_only=True)
    
    

class AddToCartSerializer(serializers.Serializer):
    """Validates the request body. The client sends only these two values."""

    product = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(
        min_value=1,
        max_value=MAX_QUANTITY_PER_ITEM,
        default=1,
    )