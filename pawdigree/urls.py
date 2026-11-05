from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

from common.views import HealthView

urlpatterns = [
    path('', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/admin/', include('accounts.admin_urls')),
    path('api/businesses/', include('businesses.urls')),
    path('api/categories/', include('categories.urls')),
    path('api/products/', include('products.urls')),
    path('api/pets/', include('pets.urls')),
    path('api/documents/', include('documents.urls')),
    path('api/adoptions/', include('adoptions.urls')),
    path('api/services/', include('services.urls')),
    path('api/favourites/', include('favourites.urls')),
    path('api/cart/', include("cart.urls")),

    path('api/schema/',SpectacularAPIView.as_view(),name='schema',),
    path('api/docs/',SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui', ),
    path('api/notification/', include('notification.urls')),
    path("api/country-codes/", include("countries.urls")),
    path('api/health/', HealthView.as_view(), name='health'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)