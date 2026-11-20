from rest_framework import serializers
from .models import MAX_QUANTITY_PER_ITEM

class CartLineSerializer(serializers.Serializer):
    """One cart line. Reads from a CartLine built by the service."""

    # source="item.id" follows  CartLine -> item -> id.
    id = serializers.IntegerField(source="item.id")
    item_type = serializers.SerializerMethodField()
    product_id = serializers.IntegerField(source="item.product_id", allow_null=True)
    pet_id = serializers.IntegerField(source="item.pet_id", allow_null=True)
    name = serializers.SerializerMethodField()
    business_name = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    quantity = serializers.IntegerField(source="item.quantity")
    line_total = serializers.DecimalField(max_digits=16, decimal_places=2)
    available = serializers.BooleanField()
    issue = serializers.CharField(allow_null=True)
    max_quantity = serializers.IntegerField()
    
    
    def get_item_type(self, obj) -> str:
        return "pet" if obj.item.pet_id else "product"

    def get_name(self, obj) -> str:
        item = obj.item
        return item.pet.name if item.pet_id else item.product.name

    def get_business_name(self, obj) -> str:
        item = obj.item
        owner = item.pet if item.pet_id else item.product
        return owner.business.name

    def get_unit_price(self, obj) -> str:
        item = obj.item
        price = item.pet.price if item.pet_id else item.product.price
        return f"{(price or 0):.2f}"

    def get_image(self, obj) -> str | None:
        # The images were prefetched.
        item = obj.item
        owner = item.pet if item.pet_id else item.product
        first = next(iter(owner.images.all()), None)
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

    product = serializers.IntegerField(min_value=1, required=False)
    pet = serializers.IntegerField(min_value=1, required=False)
    quantity = serializers.IntegerField(
        min_value=1,
        max_value=MAX_QUANTITY_PER_ITEM,
        default=1,
    )

    def validate(self, attrs):
        if ("product" in attrs) == ("pet" in attrs):
            raise serializers.ValidationError(
                "Send either product or pet, not both."
            )
        if "pet" in attrs and attrs["quantity"] != 1:
            raise serializers.ValidationError(
                {"quantity": "A pet can only be added once."}
            )
        return attrs
    
class UpdateCartItemSerializer(serializers.Serializer):
    """Validates the new quantity. Zero is refused: use DELETE to remove a line."""

    quantity = serializers.IntegerField(
        min_value=1,
        max_value=MAX_QUANTITY_PER_ITEM,
    )