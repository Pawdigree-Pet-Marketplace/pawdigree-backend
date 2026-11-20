"""Names for choice sets, so the API schema gets clear, unique enum names."""

from accounts.models import AdminAuditLog
from adoptions.models import AdoptionApplication
from businesses.models import BusinessDecision
from documents.models import BusinessDocumentReview
from orders.models import Order, VendorOrder
from reports.models import Report

AdoptionStatus = AdoptionApplication.Status
OrderStatus = Order.Status
VendorOrderStatus = VendorOrder.Status
BusinessDecisionAction = BusinessDecision.Action
AdminAuditAction = AdminAuditLog.Action
DocumentReviewAction = BusinessDocumentReview.Action
ReportStatus = Report.Status
