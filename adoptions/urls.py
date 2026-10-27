from django.urls import path

from .views import AdoptionApplicationCreateView

urlpatterns = [
    path('applications/',AdoptionApplicationCreateView.as_view(),name='adoption-application-create',),]