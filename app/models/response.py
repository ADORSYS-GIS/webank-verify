from datetime import datetime

from pydantic import BaseModel


# ── BFF contract responses (must match kycmanager/client.go exactly) ──────────

class DocSubmitResponse(BaseModel):
    submission_id: str
    status: str  # "pending" | "in_review"


class LivenessResponse(BaseModel):
    check_id: str
    status: str  # "pending" | "passed" | "failed"
    score: int


class DocumentInfo(BaseModel):
    type: str
    status: str
    date: str


class LivenessInfo(BaseModel):
    status: str
    date: str
    score: int


class DossierResponse(BaseModel):
    user_id: str
    status: str
    kyc_level: int
    updated_at: str
    documents: list[DocumentInfo] = []
    liveness_info: LivenessInfo | None = None
    rejection_message: str | None = None


class IdentityResponse(BaseModel):
    user_id: str
    person_id: str | None = None  # stable biometric key (ADR 0005); null if unknown
    kyc_level2_approved: bool = False


class ProfessionalDossierResponse(BaseModel):
    user_id: str
    professional_type: str
    status: str  # pending | in_review | approved | rejected | expired
    submitted_at: str | None = None
    reviewed_at: str | None = None
    rejection_reason: str | None = None


# ── Extended verification detail (admin dashboard) ───────────────────────────

class DocumentFields(BaseModel):
    type: str
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: str | None = None
    birth_place: str | None = None
    document_number: str | None = None
    expiry_date: str | None = None
    is_expired: bool = False
    age: int | None = None
    is_underage: bool = False
    confidence: float = 0.0


class LivenessMetrics(BaseModel):
    score: float
    face_quality: float
    face_occlusion: float
    face_luminance: float
    frames_analyzed: int
    passed: bool


class FaceMatchResult(BaseModel):
    similarity: float
    passed: bool
    distance: float = 1.0
    threshold_used: float = 0.68
    model: str = "ArcFace"


class IPAnalysis(BaseModel):
    ip: str
    country: str | None = None
    country_name: str | None = None
    city: str | None = None
    isp: str | None = None
    is_vpn: bool = False
    is_proxy: bool = False
    is_tor: bool = False
    risk_score: int = 0
    risk_flags: list[str] = []


class Warning(BaseModel):
    code: str
    message: str
    severity: str  # "info" | "warning" | "critical"


class VerificationDecision(BaseModel):
    result: str  # "approved" | "rejected" | "manual_review"
    reason: str | None = None
    requires_manual_review: bool = False


class VerificationDetail(BaseModel):
    id: str
    user_id: str
    type: str
    status: str
    doc_type: str | None = None
    country: str = "CM"
    person_id: str | None = None
    risk_score: int | None = None
    warnings: list[Warning] = []
    document: DocumentFields | None = None
    liveness: LivenessMetrics | None = None
    face_match: FaceMatchResult | None = None
    ip_intelligence: IPAnalysis | None = None
    device_info: dict | None = None
    decision: VerificationDecision | None = None
    reviewer: str | None = None
    review_notes: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class VerificationListItem(BaseModel):
    id: str
    user_id: str
    status: str
    doc_type: str | None = None
    country: str = "CM"
    risk_score: int | None = None
    warning_count: int = 0
    created_at: datetime


class VerificationListResponse(BaseModel):
    items: list[VerificationListItem]
    total: int
    page: int
    page_size: int


class AdminStats(BaseModel):
    total: int
    pending: int
    approved: int
    rejected: int
    manual_review: int
    approved_today: int
    rejected_today: int


class WebhookDelivery(BaseModel):
    id: str
    event_type: str
    target_url: str | None = None
    http_status: int | None = None
    attempt: int
    delivered_at: datetime
