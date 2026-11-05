from rest_framework.throttling import AnonRateThrottle


class GuestAddThrottle(AnonRateThrottle):
    """Limits how fast one visitor who is not logged in can add to a cart.
    AnonRateThrottle only counts anonymous requests, so logged-in customers are not affected."""

    scope = "guest_cart"

    def get_rate(self):
        # Written here so no project setting is needed.
        return "30/min"