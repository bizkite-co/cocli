# Video encode profiles (draft vs publish)

One normalize path (`cocli video normalize` / `add --normalize`) with selectable
quality/speed settings. Profile is recorded on `VideoJobRun.settings.profile`
and the concrete encoder/preset/CRF/CQ for A/B diagnosis.

## Built-in profiles

| Profile   | libx264              | h264_nvenc           | Intent |
|-----------|----------------------|----------------------|--------|
| `publish` | preset `slow`, CRF 18 | preset `p4`, CQ 20  | **Default.** Best text clarity for UI/screencasts; longer CPU encodes. |
| `draft`   | preset `veryfast`, CRF 20 | preset `p2`, CQ 23 | Faster review passes; small UI text usually still readable. |

Tradeoffs for screencasts / IDE UIs:

- **CRF 18 + slow** keeps thin fonts and anti-aliased code sharp; wall-clock can be
  high on CPU when nvenc is unavailable.
- **draft** raises CRF slightly and uses a fast preset: much quicker, mild softness
  on the finest glyphs. Prefer `publish` for the final YouTube encode.

Encoder selection is unchanged: prefer `h264_nvenc` when the runtime probe
succeeds; otherwise `libx264`. Profile only changes quality knobs, not the
fallback policy.

## CLI

```bash
# Draft pass (fast)
cocli video normalize -c my-campaign --profile draft
cocli video add /path/to/clip.mp4 -c my-campaign --normalize --profile draft

# Publish (default if omitted)
cocli video normalize -c my-campaign --profile publish
```

## Campaign config

```toml
[video.encode]
profile = "publish"   # default when CLI --profile omitted

# Optional per-profile overrides
[video.encode.profiles.draft]
libx264_preset = "fast"
libx264_crf = 21
nvenc_preset = "p3"
nvenc_cq = 22
```

Resolution order: **CLI `--profile` > `video.encode.profile` > `publish`**.

## Job-run fingerprint

Under `video/job_runs/{YYYYMMDD}/{run_id}.json` (and `last-normalize-run.json`):

```json
"settings": {
  "encoder": "libx264",
  "encoder_requested": "h264_nvenc",
  "encoder_fallback_reason": "cuInit failed ...",
  "profile": "draft",
  "preset": "veryfast",
  "crf": 20,
  "cq": null
}
```
