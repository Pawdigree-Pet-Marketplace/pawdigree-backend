from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path('', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/businesses/', include('businesses.urls')),
    path('api/categories/', include('categories.urls')),
    path('api/pets/', include('pets.urls')),
    path('api/documents/', include('documents.urls')),
    path('api/adoptions/', include('adoptions.urls')),

    path('api/schema/',SpectacularAPIView.as_view(),name='schema',),
    path('api/docs/',SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui', ),
    path("api/notifications/", include("notification.urls")),
    path("api/country-codes/", include("countries.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)