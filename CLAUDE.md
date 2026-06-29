# CLAUDE.md — webank-verify

## 🌐 Webank ecosystem (read first)
This repo is part of a multi-service ecosystem. The **single source of truth** for the map,
the inter-service contracts, and the decision log lives in **`webank-context`**
(`ADORSYS-GIS/webank-context`, cloned alongside this repo). Before cross-repo or
contract-touching work, read its `ECOSYSTEM.md`, `topology/contracts.md`, and `decisions/`.

Must-know services: **webank-mobile** (Flutter app + Go BFF, device-bound JWS, no RBAC) ·
**webank-verify** (this repo — canonical KYC) · **fineract-aml** (AML/scoring/cases) ·
**fineract-apps** (Fineract frontends + payment/asset services). 🪦 `webank-kyc-manager` is
**deprecated** — this repo replaces it (ADR 0001).

**Recurring guardrails:** money is integer/basis-points, never float · fail-closed on
security/compliance checks · contract changes need an ADR + a consumer check.

---

## ⭐ This repo is the CANONICAL KYC / identity service
All KYC/identity work goes here — never to `webank-kyc-manager`. **Default branch: `master`.**

## Stack & layout
- Python / FastAPI + a React operator dashboard (`dashboard/`).
- Entrypoint `app/main.py`. Routers in `app/api/`:
  - `admin.py` — operator review (approve/reject), stats, webhook log. **Emits KYC webhooks.**
  - `document.py` — doc submission (runs biometric dedup on submit).
  - `liveness.py`, `professional.py`, `dossier.py`, `recovery.py`, `health.py`.
- Services in `app/services/`:
  - `ocr_service.py` — Cameroon CNI (easyocr + regex).
  - `mrz_service.py` — passport TD3 MRZ parser.
  - `liveness_service.py` — selfie-frame liveness (doc-agnostic).
  - `face_service.py` — biometric dedup (`check_duplicate`) + `person_id` clustering
    (`match_or_mint_person_id`, ArcFace cosine vs approved).
  - `person_service.py` — assigns/resolves the stable `person_id` (ADR 0005).
  - `risk_service.py`, `ip_service.py`, `storage_service.py`, `webhook_service.py`.
- Core in `app/core/`: `auth.py`, `config.py`, `db.py`, `redis.py`.
- Models in `app/models/` (`db.py`, `request.py`, `response.py`).

## Conventions & known constraints
- **Doc types:** `passport`, CNI, and `recepisse` (ADR 0007). Passport is the only
  MRZ-bearing type; CNI and récépissé share the French OCR pipeline. Anything else maps
  to CNI. Don't dedup on document number — identity continuity across types is the
  biometric `person_id`, not the number (ADR 0005).
- **`person_id`** (ADR 0005): stable face-cluster identity key. Assigned on document
  **approval** (`person_service.assign_person_id` → `face_service.match_or_mint_person_id`,
  reuse-or-mint vs other approved `person_id`s), stored on `Verification.person_id`, emitted
  in the KYC webhook `data`, and pullable via `GET /identity/{user_id}`. **Null when no face
  was extracted → omitted from the webhook → consumers must fail closed.** Per-account dedup
  is enforced *downstream* (`UNIQUE(person_id)`), not at source.
- **Webhooks** (`webhook_service.py`): HMAC-SHA256 over the canonical JSON body
  (`X-Webank-Signature: sha256=...`); envelope `{id, event, timestamp, data}`; 3 retries
  `[1,5,15]s`; logged to `webhook_deliveries`. Events `kyc.level2.approved` /
  `kyc.level2.rejected` (2-level KYC model: document + liveness combined); `data` carries
  `person_id` when known. Exact contract: `webank-context/topology/contracts.md`.
- **Dedup warning** (`check_duplicate`) is still an operator *warning* only, in-memory (no
  vector index) — fine at current scale; revisit with a vector index if the approved set grows.
- **Fail closed** on identity/liveness checks.

## Python conventions
Follow the fineract-apps Python conventions (type hints, specific exceptions, f-strings,
`ruff`/`mypy`). FastAPI: Pydantic schemas per operation, `Depends()` DI, async I/O drivers.
