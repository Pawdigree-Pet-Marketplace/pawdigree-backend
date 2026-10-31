class NoStoreForAuthenticatedMiddleware:
    """Stop browsers and proxies keeping copies of private API responses.

    Covers requests that carry a token, every /api/auth/ response (these
    hold tokens and one-time codes), and any 401 or 403 response. Public
    listings sent without a token stay cacheable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/api/"):
            return response
        if self._is_private(request, response):
            response["Cache-Control"] = "no-store"
            response["Pragma"] = "no-cache"
        return response

    @staticmethod
    def _is_private(request, response):
        return (
            bool(request.headers.get("Authorization"))
            or request.path.startswith("/api/auth/")
            or response.status_code in (401, 403)
        )