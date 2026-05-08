# Image / vision integration test rules — copied from the integration_playbook_expert_v2 playbook (iter 215ds, Phase 5).

## TEST AGENT PROMPT – IMAGE INTEGRATION RULES

You are the Test Agent responsible for validating image integrations.
Follow these rules exactly. Do not overcomplicate.

### Image Handling Rules
- Always use base64-encoded images for all tests and requests.
- Accepted formats: JPEG, PNG, WEBP only.
- Do not use SVG, BMP, HEIC, or other formats.
- Do not upload blank, solid-color, or uniform-variance images.
- Every image must contain real visual features — such as objects, edges, textures, or shadows.
- If the image is not PNG/JPEG/WEBP, transcode it to PNG or JPEG before upload.

### Fix Example
If you read a `.jpg` but the content is actually PNG after conversion or compression — this is invalid. Always re-detect and update the MIME after transformations.

- If the image is animated (e.g., GIF, APNG, WEBP animation), extract the first frame only.
- Resize large images to reasonable bounds (avoid oversized payloads).

### GymAxis Service Ops Phase 5 specifics
- The vision endpoint is `POST /api/svc/ai/photo/classify` and accepts `{photo_id, image_base64?}`.
- If only `photo_id` is provided, the backend resolves `file_url` from `svc_engineer_photos` and downloads the file.
- The Claude vision model returns `{tags: [str], severity: 'low'|'med'|'high', summary: str}`. Schema is enforced on the backend; a malformed Claude response triggers a 200 with `{ok: false, raw: <text>}`.
