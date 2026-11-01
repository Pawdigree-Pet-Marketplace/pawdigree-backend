import uuid

import pytest
from django.urls import reverse

UNAUTHORIZED = 401
FORBIDDEN = 403
OK = 200
BAD_REQUEST = 400
NOT_FOUND = 404

MISSING_ID = 999999

# (case name, method, url name, url kwargs, expected status per role).
# For endpoints that need a body, an empty one is sent: a user who passes
# the permission check gets 400 (validation) or 404 (unknown id), while a
# user who does not gets 401 or 403.
CASES = [
    (
        "business-list", "get", "business-list", {},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": OK, "admin": FORBIDDEN, "system_admin": FORBIDDEN,
        },
    ),
    (
        "business-register", "post", "business-register", {},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": BAD_REQUEST, "admin": FORBIDDEN,
            "system_admin": FORBIDDEN,
        },
    ),
    (
        "pet-list", "get", "pet-list", {},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": OK, "admin": FORBIDDEN, "system_admin": FORBIDDEN,
        },
    ),
    (
        "pet-deactivate", "delete", "pet-detail", {"pk": MISSING_ID},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": NOT_FOUND, "admin": FORBIDDEN,
            "system_admin": FORBIDDEN,
        },
    ),
    (
        "pet-admin-deactivate", "delete", "pet-admin-detail",
        {"pk": MISSING_ID},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": FORBIDDEN, "admin": NOT_FOUND,
            "system_admin": NOT_FOUND,
        },
    ),
    (
        "admin-register", "post", "admin-register", {},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": FORBIDDEN, "admin": FORBIDDEN,
            "system_admin": BAD_REQUEST,
        },
    ),
    (
        "administrator-list", "get", "administrator-list", {},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": FORBIDDEN, "admin": FORBIDDEN, "system_admin": OK,
        },
    ),
    (
        "administrator-create", "post", "administrator-list", {},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": FORBIDDEN, "admin": FORBIDDEN,
            "system_admin": BAD_REQUEST,
        },
    ),
    (
        "administrator-detail", "get", "administrator-detail",
        {"pk": MISSING_ID},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": FORBIDDEN, "admin": FORBIDDEN,
            "system_admin": NOT_FOUND,
        },
    ),
    (
        "administrator-activate", "post", "administrator-activate",
        {"pk": MISSING_ID},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": FORBIDDEN, "admin": FORBIDDEN,
            "system_admin": NOT_FOUND,
        },
    ),
    (
        "administrator-deactivate", "post", "administrator-deactivate",
        {"pk": MISSING_ID},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": FORBIDDEN, "admin": FORBIDDEN,
            "system_admin": NOT_FOUND,
        },
    ),
    (
        "category-create", "post", "category-list", {},
        {
            "anonymous": UNAUTHORIZED, "customer": FORBIDDEN,
            "vendor": FORBIDDEN, "admin": BAD_REQUEST,
            "system_admin": BAD_REQUEST,
        },
    ),
    (
        "customer-profile", "get", "customer-profile", {},
        {
            "anonymous": UNAUTHORIZED, "customer": OK,
            "vendor": FORBIDDEN, "admin": FORBIDDEN,
            "system_admin": FORBIDDEN,
        },
    ),
    (
        "current-user", "get", "current-user", {},
        {
            "anonymous": UNAUTHORIZED, "customer": OK, "vendor": OK,
            "admin": OK, "system_admin": OK,
        },
    ),
    (
        "logout", "post", "logout", {},
        {
            "anonymous": UNAUTHORIZED, "customer": BAD_REQUEST,
            "vendor": BAD_REQUEST, "admin": BAD_REQUEST,
            "system_admin": BAD_REQUEST,
        },
    ),
    (
        "pet-public-list", "get", "pet-public-list", {},
        {
            "anonymous": OK, "customer": OK, "vendor": OK,
            "admin": OK, "system_admin": OK,
        },
    ),
    (
        "category-read", "get", "category-list", {},
        {
            "anonymous": OK, "customer": OK, "vendor": OK,
            "admin": OK, "system_admin": OK,
        },
    ),
]


def build_rows():
    for name, method, url_name, kwargs, expected in CASES:
        for role, status_code in expected.items():
            yield pytest.param(
                method, url_name, kwargs, role, status_code,
                id=f"{name}-{role}",
            )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "method, url_name, kwargs, role, expected_status",
    list(build_rows()),
)
def test_endpoint_access_by_role(
    api_client, request, method, url_name, kwargs, role, expected_status
):
    if role != "anonymous":
        api_client.force_authenticate(user=request.getfixturevalue(role))

    url = reverse(url_name, kwargs=kwargs)
    send = getattr(api_client, method)

    if method == "post":
        response = send(url, {}, format="json")
    else:
        response = send(url)

    assert response.status_code == expected_status


DOCUMENT_ROWS = [
    # (role, upload status, download status)
    ("anonymous", 401, 401),
    ("customer", 403, 403),
    ("vendor", 400, 403),
    ("admin", 403, 404),
    ("system_admin", 403, 404),
]


@pytest.mark.django_db
@pytest.mark.parametrize("role, upload_status, download_status", DOCUMENT_ROWS)
def test_document_endpoints_access_by_role(
    api_client, request, role, upload_status, download_status
):
    if role != "anonymous":
        api_client.force_authenticate(user=request.getfixturevalue(role))

    # The upload view only accepts multipart bodies, so send one (empty).
    upload = api_client.post(
        reverse("business-document-upload"), {}, format="multipart"
    )
    download = api_client.get(
        reverse(
            "business-document-download",
            kwargs={"document_id": uuid.uuid4()},
        )
    )

    assert upload.status_code == upload_status
    assert download.status_code == download_status
