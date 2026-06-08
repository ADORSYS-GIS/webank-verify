from pydantic import BaseModel, Field


class DocumentSubmitRequest(BaseModel):
    user_id: str
    images: list[str] = Field(..., min_length=1, description="Base64-encoded images (front required, back optional)")
    doc_type: str = Field(..., description="'national_id' or 'passport'")
    client_ip: str | None = None
    user_agent: str | None = None


class LivenessVerifyRequest(BaseModel):
    user_id: str
    frames: list[str] = Field(..., min_length=1, description="Base64-encoded JPEG frames")
    context: str = Field(default="kyc", description="'kyc' or 'recovery'")
    client_ip: str | None = None
    user_agent: str | None = None


class ProfessionalSubmitRequest(BaseModel):
    user_id: str
    professional_type: str = Field(..., description="'AGENT' or 'MERCHANT'")
    documents: dict[str, str] = Field(default_factory=dict, description="Document name → base64 image")
    metadata: dict[str, str] = Field(default_factory=dict)


class RecoveryQueueRequest(BaseModel):
    user_id: str


class AdminApproveRequest(BaseModel):
    notes: str | None = None


class AdminRejectRequest(BaseModel):
    reason: str
    fraud_flag: bool = False
