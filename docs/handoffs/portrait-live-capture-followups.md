# 001 — Live-sitting capture: hardware validation + booth kiosk hardening

- **Status**: TODO
- **Commit**: (see `cursor/portrait-live-capture-ddd2`)
- **Severity**: LOW (the feature works end-to-end for the sitting-in-front-of-a-laptop case; this ticket is about the booth-hardware edge cases that can't be validated in this sandbox)
- **Category**: PortraitBot, live sitting / booth
- **Estimated scope**: manual hardware testing + 1-2 small JS tweaks likely, not a rewrite

## What's already done (do not redo)

`botdraw/web/app.js` + `botdraw/web/styles.css` on this branch: a "Take photo…" button next to the PortraitBot file picker opens a `getUserMedia` capture overlay (live preview, mirrored like a selfie camera, Capture → Retake/Use photo), and on confirm produces a `File` fed through the **exact same** `applyPortraitSourceFile()` path a file-picker selection uses — no separate ingest code path for camera vs. upload. Captured frames are downscaled to the same 1280px max side the existing upload path already uses (`downscalePortraitForUpload`), for the same proxy/multipart-size reason.

Verified via `computerUse` in this sandbox (no camera hardware available here):
- Button renders in the Dev Panel.
- Clicking it opens the overlay.
- With no camera present, `getUserMedia` rejects and the overlay shows a clear inline error ("No camera was found on this device...") instead of a blank/broken video element, with Capture hidden and Cancel still working.
- Cancel closes the overlay cleanly with no lingering DOM/JS errors, and always stops any acquired media stream tracks.

**Not verified here, because no camera hardware exists in this sandbox**: the actual happy path — permission grant → live video → Capture → Retake → Use photo → ingest. This is real, load-bearing functionality that a code read cannot substitute for testing.

## Problem / what's left

1. **Hardware validation on a machine with a real camera.** Run through: grant permission → confirm live video renders (not just a black box) → Capture → confirm the still frame looks right → Retake → Use photo → confirm ingest runs and produces a sane result.

   On mirroring specifically: the CSS `transform: scaleX(-1)` is applied only to the `<video>` preview element for a natural "looking in a mirror" feel while framing. `canvas.drawImage(video, ...)` in `captureBtn.onclick` samples the underlying decoded video frame, not the CSS-transformed rendering — CSS transforms don't affect what `drawImage` reads from a `<video>` source. So the intended behavior is: **live preview mirrored, saved photo not mirrored** (matching standard camera-app convention — a saved selfie shouldn't have your text/asymmetric features backwards). Confirm this actually holds on real hardware; if the saved photo comes out mirrored anyway, something about how the specific browser/camera driver exposes the stream is behaving unexpectedly, and the fix would be an explicit `ctx.translate(w,0); ctx.scale(-1,1)` (or its removal) in the capture handler.
2. **Booth kiosk framing.** The plan's context is a booth setup (per `AGENTS.md`'s "pixinks" drawbot references), likely a tablet/kiosk rather than someone's laptop webcam. Things to check on real booth hardware:
   - Does `facingMode: "user"` resolve to the correct camera on the actual kiosk device (front vs. rear, if the device has both)? A booth likely wants whichever camera faces the sitter.
   - Should there be an on-screen countdown ("3… 2… 1… 📸") before capture, so the sitter has time to pose? Right now Capture fires instantly on click/tap. This is a real UX gap for a booth (nobody minds an instant capture at a laptop; a walk-up booth sitter needs a moment).
   - Touch-target sizing: the Capture/Retake/Use photo/Cancel buttons use the existing `.btn`/`.btn-ghost`/`.btn-primary` classes sized for desktop rail use, not necessarily large enough for a touchscreen kiosk. Measure against the actual device.
3. **The plan explicitly says a few minutes of processing is acceptable live**, so no fast-path/latency work is needed here — confirm that assumption still holds once this is tested against real studio-quality render times end-to-end from a booth operator's perspective (capture → ingest → render → plot-ready), not just the ingest/render benchmarks already covered by `tests/test_portrait_ingest.py`'s timing assertions.

## Repo conventions to follow

- `applyPortraitSourceFile()` (in `renderPortrait()`, `botdraw/web/app.js`) is the single reset/redraw path both upload and capture already funnel through — any capture-flow fix belongs in `openPortraitCameraCapture()`, not in a new parallel ingest path.
- Camera UI styling lives in `botdraw/web/styles.css` under the `/* Live-sitting camera capture overlay */` comment block, using the existing DESIGN.md token variables (`--panel`, `--radius`, `--paper-shadow`, `--ease`, `--dur`) — don't hardcode new colors/timings.
- This repo has **no JavaScript test framework** (no `package.json`, no jest/playwright/vitest) — verification for this ticket is necessarily manual (`computerUse` or a real device), not something to try to shoehorn into `pytest`.

## Steps

1. On a machine/device with a real camera, run `botdraw serve` and manually complete the full capture flow described in Problem item 1. Screenshot or video each step.
2. If mirroring is wrong (captured photo comes out flipped when it shouldn't, or vice versa), fix in `openPortraitCameraCapture()`'s `captureBtn.onclick` — mirror the canvas draw (`ctx.translate(w,0); ctx.scale(-1,1)` before `drawImage`) or remove the CSS mirror on `.camera-video`, whichever produces a correctly-oriented saved photo. Keep the *live preview* feeling natural (mirrored, like looking in a mirror) even if the saved file should or shouldn't be mirrored — these are two independent decisions.
3. If a countdown is wanted, add it as a state in `openPortraitCameraCapture()` between clicking Capture and actually drawing the canvas frame (e.g. show "3", "2", "1" text over `.camera-stage` for ~1s each, then capture) — self-contained within that function, no new global state needed.
4. Confirm/adjust `facingMode` based on actual kiosk hardware behavior.

## Boundaries

- Do NOT change `applyPortraitSourceFile()`'s ingest-reset semantics — that logic is shared with file upload and already correct; camera capture should keep looking identical to an upload from ingest onward.
- Do NOT add a JS test framework to the repo just for this ticket — that's a much larger decision (build tooling, CI changes) than this ticket's scope.
- If real hardware isn't available to you either, say so explicitly in your handoff rather than silently shipping unverified — this is exactly the situation this ticket exists to flag.

## Verification

- **Mechanical**: `node --check botdraw/web/app.js` (syntax only — this repo has no JS test runner). `pytest tests/` should be unaffected (this is a JS/CSS-only surface).
- **Feel check** (on real hardware): grant camera permission, confirm live video is not flipped/broken, capture a frame, confirm the still preview looks correct (not mirrored wrong, not rotated), retake at least once to confirm state resets cleanly, then Use photo and confirm the PortraitBot ingest step receives it exactly as it would an uploaded file (crop/auto-frame/style selection all still work normally afterward).
- **Done when**: a person can sit down at the actual booth hardware, tap "Take photo…", see themselves, capture, and get a print-ready portrait through the same pipeline as an uploaded photo — with no visible orientation/mirroring bug.
