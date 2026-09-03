# DingTalk S3 Image Notification Implementation Plan

**Goal:** Make the existing daily 10:30 credit-attribution notification upload its generated PNG screenshot to S3 and send the public image URL to DingTalk without exposing the private dashboard URL.

**Architecture:** Keep screenshot capture, Level3-only digest generation, and the notification ledger unchanged. Add a small S3 PNG adapter with environment-only credentials; the daily Dagster op uploads the captured PNG and sends an `image` Webhook message containing the S3 URL. If the adapter is not configured, retain the existing signed Webhook Markdown path as a safe fallback.

**Tech Stack:** Python, boto3, requests, Dagster, pytest, existing notification module.

## Global Constraints

- Never commit AWS, DingTalk, or conversion-service credentials.
- S3 object names must be deterministic per PT and timestamped to avoid overwriting a prior report.
- DingTalk receives only a publicly reachable HTTPS PNG URL, never a local file path or private dashboard URL.
- The existing 10:30 Asia/Shanghai schedule and once-per-PT ledger behavior remain unchanged.

### Task 1: Add the S3 PNG/Webhook adapter

**Files:**
- Modify: `server/attribution_notification.py`
- Test: `server/test_attribution_notification.py`

Add `S3PngDingTalkNotifier` with injectable S3 client and HTTP session. It uploads the captured PNG with `boto3`, builds the public S3 URL, then POSTs a signed `{msgtype: image, image: {picURL}}` payload to the Webhook. It must raise on upload or HTTP/API errors and never log credentials.

### Task 2: Route the daily job through the adapter

**Files:**
- Modify: `server/pipeline/dagster_defs.py`
- Modify: `server/.env.example`
- Test: `server/test_attribution_notification.py`

When S3 bucket and Webhook settings are present, upload the generated PNG and send the image message. Otherwise use the existing Webhook Markdown sender. Keep the current report screenshot and ledger handling.

### Task 3: Verify configuration and scheduling

**Files:**
- Test: `server/test_dingtalk_schedule.py`

Add tests for configuration selection, missing-setting fallback, PNG upload payload, signed image message, API error handling, and preservation of the 10:30 schedule. Run the focused notification tests and the existing server test suite relevant to this area.
