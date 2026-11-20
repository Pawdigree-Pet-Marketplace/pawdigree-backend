from rest_framework.pagination import PageNumberPagination


class VendorTransactionPagination(PageNumberPagination):
    """Vendor transaction lists: 20 per page by default, 50 at most."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50
