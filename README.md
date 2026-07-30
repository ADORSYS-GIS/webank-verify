# webank-verify

Identity verification microservice for Cameroon — Didit.me-style KYC engine built on open-source ML.

> CI builds and pushes Docker images to GHCR on every merge to `master` (tagged `:latest`) and `develop` (tagged `:develop`).

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

## Relationship to webank-kyc-manager (deprecated)

webank-verify replaces the deprecated `webank-kyc-manager` service for identity
verification (document OCR, liveness, biometric dedup). It is **not** a drop-in
replacement — the BFF uses a separate `webankverify` client
(`bff/internal/webankverify/client.go`) pointed at `WEBANK_VERIFY_BASE_URL`.

OTP delivery is handled by a separate SMS gateway service
(`fineract-adorsys-sms-gateway`) via `SMS_GATEWAY_BASE_URL`.

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

## Asynchronous KYC processing

`POST /document/submit` and `POST /liveness/verify` validate the submitted S3
objects, persist a `processing` verification, and return `202 Accepted` with
`{"verification_id": "…", "status": "processing"}`. OCR, ArcFace, and
liveness analysis run on one dedicated inference thread in the single uvicorn
worker;
the event loop remains available for `/health` and webhook delivery. Models are
warmed with a dummy inference at application startup.

The job registry and inference executor are process-local by design. Keep one
uvicorn worker per replica; increasing worker or replica counts multiplies the
ML memory/CPU budget and queues work independently. A durable shared queue is
required before using this service as a horizontally scaled job worker.

The terminal decision remains the existing signed webhook (`kyc.level2.approved`
or `kyc.level2.rejected`). `manual_review` continues through the operator flow,
which is unchanged. This matches the BFF's [202 decoupling PR #262](https://github.com/ADORSYS-GIS/webank-mobile/pull/262)
and its [source issue #261](https://github.com/ADORSYS-GIS/webank-mobile/issues/261).

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
