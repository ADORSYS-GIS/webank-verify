from fastapi.routing import APIRoute

from app.api.document import router as document_router
from app.api.liveness import router as liveness_router
from app.models.response import AcceptedVerificationResponse


def _post_route(router, path: str) -> APIRoute:
    return next(
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == path and "POST" in route.methods
    )


def test_document_submission_uses_async_consumer_contract():
    route = _post_route(document_router, "/document/submit")

    assert route.status_code == 202
    assert route.response_model is AcceptedVerificationResponse
    assert AcceptedVerificationResponse.model_validate(
        {"verification_id": "v1", "status": "processing"}
    ).model_dump() == {"verification_id": "v1", "status": "processing"}


def test_liveness_submission_uses_async_consumer_contract():
    route = _post_route(liveness_router, "/liveness/verify")

    assert route.status_code == 202
    assert route.response_model is AcceptedVerificationResponse
