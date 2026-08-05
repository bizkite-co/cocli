# Video GPU path (WSL2 + CUDA): encode + Whisper

Normalize already **probes** hardware and falls back safely:

| Stage | Prefer when CUDA works | Fallback |
|-------|------------------------|----------|
| Encode | `h264_nvenc` (runtime probe encodes a null frame) | `libx264` |
| Whisper | `device=cuda`, `compute_type=float16` | `device=cpu`, `compute_type=int8` |

Job runs record:

- **Encode:** `settings.encoder`, `encoder_requested`, `encoder_fallback_reason`, `profile`, preset/CRF/CQ
- **STT:** `stt.device`, `stt.compute_type`, `stt.model`, `stt.provider` when Whisper (or dual) runs

## Enable NVIDIA GPU in WSL2

1. **Windows host:** recent Game Ready / Studio driver with WSL support
   (see [NVIDIA CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)).
2. **WSL2** (not WSL1): `wsl --status` / `uname -a`.
3. Inside WSL, verify:

   ```bash
   nvidia-smi
   ```

4. **FFmpeg with nvenc:** system or distro build that lists `h264_nvenc`:

   ```bash
   ffmpeg -hide_banner -encoders | grep nvenc
   ```

   cocli probes usability; if `cuInit` fails you still get libx264 automatically.

5. **faster-whisper CUDA:** install a CUDA-capable PyTorch / ctranslate2 stack
   matching the GPU driver (see faster-whisper docs). When CUDA load fails,
   Whisper logs a warning and uses CPU int8.

## Validation checklist

```bash
nvidia-smi
ffmpeg -hide_banner -encoders | grep h264_nvenc
# After a normalize with Whisper:
# job_run settings.encoder == h264_nvenc (if probe OK)
# job_run stt.device == cuda (if Whisper CUDA load OK)
```

## Campaign notes

```toml
[video.transcription]
provider = "whisper"          # or "both" / "gemini"
whisper_model = "small"       # larger models benefit more from CUDA
```

If GPU is unavailable, no config change is required: both encode and Whisper
fall back and the receipt explains which path was used.
