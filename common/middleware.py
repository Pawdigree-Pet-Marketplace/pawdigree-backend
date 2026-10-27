class NoStoreForAuthenticatedMiddleware:
    """Stop browsers from keeping copies of logged-in API responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/") and request.headers.get(
            "Authorization"
        ):
            response["Cache-Control"] = "no-store"
        return response