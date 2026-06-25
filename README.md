# webank-verify

Identity verification microservice for Cameroon — Didit.me-style KYC engine built on open-source ML.

## What it does

- **Document OCR**: Extract NOM, PRENOM, DOB, N°, expiry from Cameroonian CNI, récépissé and Passeport (easyocr, French)
- **MRZ parsing**: Machine-readable zone extraction from passports
- **Face matching**: Selfie vs ID photo comparison using deepface ArcFace (similarity score)
- **Passive liveness detection**: Multi-frame analysis — liveness score, face quality, occlusion, luminance
- **Duplicate face detection**: Warn when a face matches an existing approved user
- **Stable biometric `person_id`**: One key per real person (face-cluster), assigned on document approval and emitted in the KYC webhook for downstream identity dedup (ADR 0005)
- **IP intelligence**: Geolocation (MaxMind GeoLite2), VPN/proxy/Tor detection
- **Fraud risk scoring**: Weighted aggregate (0–100) with warnings engine
- **Operator dashboard**: Didit.me-style React SPA for reviewing and approving verifications
- **Webhook delivery**: HMAC-SHA256 signed events to the BFF (kyc.level2.approved, etc.)
- **Audit trail**: Full event log for every verification

## Drop-in replacement for webank-kyc-manager

Implements the exact same API contract as `webank-mobile/bff/internal/kycmanager/client.go`. Point the BFF at this service via `KYC_MANAGER_BASE_URL`.

## Quick start

```bash
cp .env.example .env
# Edit .env with your settings

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8070

# Admin dashboard
open http://localhost:8070/admin

# Health check
curl http://localhost:8070/health
```

## Docker

```bash
docker compose up
```

## API contract

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/document/submit` | OCR + face extract + queue for review |
| POST | `/liveness/verify` | Liveness + face match + auto-score |
| GET | `/dossier/{user_id}` | Dossier state for BFF |
| GET | `/identity/{user_id}` | Stable biometric `person_id` for downstream dedup (ADR 0005) |
| POST | `/professional/submit` | KYC4 professional dossier |
| GET | `/professional/status/{user_id}` | KYC4 status |
| POST | `/recovery/queue` | Queue manual recovery review |
| GET | `/health` | Health check |

All BFF-facing endpoints require `X-KYC-Api-Key` header.  
Admin endpoints require `Authorization: Bearer <ADMIN_SECRET>`.

## Repository

Part of the Webank ecosystem: [ADORSYS-GIS/webank-mobile](https://github.com/ADORSYS-GIS/webank-mobile)
