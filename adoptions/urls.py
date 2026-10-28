from django.urls import path

from .views import (
    AdoptionApplicationCreateView,
    AdoptionApplicationDecisionView,
)
urlpatterns = [
    path('applications/',AdoptionApplicationCreateView.as_view(),name='adoption-application-create',),
    path('applications/<uuid:application_id>/decision/',AdoptionApplicationDecisionView.as_view(),name='adoption-application-decision',),]