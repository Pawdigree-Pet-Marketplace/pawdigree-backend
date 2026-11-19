from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Report
from .serializers import ReportResponseSerializer, ReportSubmissionSerializer


@extend_schema(
    tags=["reports"],
    summary="Submit a report",
    description=(
        "Authentication is required. The authenticated user is assigned as "
        "the reporter automatically. Report status is assigned by the server "
        "and defaults to PENDING."
    ),
    request=ReportSubmissionSerializer,
    responses={201: ReportResponseSerializer},
)
class ReportCreateView(generics.GenericAPIView):
    serializer_class = ReportSubmissionSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = Report.objects.create(
            reporter=request.user,
            **serializer.validated_data,
        )
        return Response(
            ReportResponseSerializer(report).data,
            status=status.HTTP_201_CREATED,
        )
