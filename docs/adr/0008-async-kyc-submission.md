# ADR 0008: Asynchronous KYC submission contract

## Status

Accepted

## Context

The CPU-bound OCR, face, and liveness pipeline can take minutes on a CPU. The
webank-mobile BFF therefore cannot hold the app request open while
webank-verify performs inference. The terminal decision already has an
independent signed webhook path.

Source of truth: [webank-mobile PR #262](https://github.com/ADORSYS-GIS/webank-mobile/pull/262)
and [issue #261](https://github.com/ADORSYS-GIS/webank-mobile/issues/261).

## Decision

`POST /document/submit` and `POST /liveness/verify` validate the S3 objects,
persist the verification as `processing`, enqueue the work, and return HTTP
202. The response is:

```json
{"verification_id":"<uuid>","status":"processing"}
```

Inference runs in a bounded per-process executor. The process uses one uvicorn
worker and one inference thread; model warmup occurs during FastAPI startup.
The final outcome remains the existing signed `kyc.level2.approved` or
`kyc.level2.rejected` webhook. Manual review remains operator-driven.

## Compatibility and consumer check

The old synchronous response fields (`submission_id`, `check_id`, and liveness
`score`) are intentionally removed because the BFF ignores the synchronous
verdict and waits for the webhook. The consumer contract is checked by
`tests/test_async_contract.py`, which asserts both route response models and
the 202 status code. The BFF implementation and tests are tracked in PR #262.

## Failure recovery

Jobs are process-local, so startup sweeps rows left in `processing` after a
crash or redeploy, marks them `manual_review`, records a recovery event, and
clears any liveness processing marker as failed. Operators can then review the
record rather than leaving users stuck on an indefinite 202 response.
