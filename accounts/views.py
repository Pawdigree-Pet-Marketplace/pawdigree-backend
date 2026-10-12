from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from accounts.permissions import IsCustomer, IsVendor

from .serializers import (
    CustomerLoginSerializer,
    CustomerRegistrationSerializer,
    LogoutSerializer,
    VendorLoginSerializer,
    VendorRegistrationSerializer,
    CustomerProfileSerializer,
    
)


@extend_schema(
    summary='Register a customer',
    description=(
        'Creates a new customer account. '
        'No authentication is required.'
    ),
)
class CustomerRegistrationView(generics.CreateAPIView):
    serializer_class = CustomerRegistrationSerializer
    permission_classes = (AllowAny,)


@extend_schema(
    summary='Register a vendor',
    description=(
        'Creates a new vendor account. '
        'No authentication is required.'
    ),
)
class VendorRegistrationView(generics.CreateAPIView):
    serializer_class = VendorRegistrationSerializer
    permission_classes = (AllowAny,)


@extend_schema(
    summary='Customer login',
    description=(
        'Authenticates a customer using email and password '
        'and returns an access token and refresh token.'
    ),
)
class CustomerLoginView(generics.GenericAPIView):
    serializer_class = CustomerLoginSerializer
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return Response({
            'access': serializer.validated_data['access'],
            'refresh': serializer.validated_data['refresh'],
        })


@extend_schema(
    summary='Vendor login',
    description=(
        'Authenticates a vendor using email and password '
        'and returns an access token and refresh token.'
    ),
)
class VendorLoginView(generics.GenericAPIView):
    serializer_class = VendorLoginSerializer
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return Response({
            'access': serializer.validated_data['access'],
            'refresh': serializer.validated_data['refresh'],
        })


@extend_schema(
    summary='Logout',
    description=(
        'Logs out the authenticated user by blacklisting '
        'the provided refresh token.'
    ),
)
class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return Response(
            {'detail': 'Successfully logged out.'},
        )
        
class CustomerProfileView(generics.RetrieveUpdateAPIView): #this view allows customers to retrieve and update their profile information
    serializer_class = CustomerProfileSerializer 
    permission_classes = (IsAuthenticated, IsCustomer) #only authenticated customers can access this view

    def get_object(self): #this method retrieves the currently authenticated user object
        return self.request.user


class CurrentUserView(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        user = request.user

        return Response({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone': user.phone,
            'role': user.role,
        })