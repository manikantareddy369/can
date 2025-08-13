# Insurer Solvency Explainer Video

This project generates a 1080p slideshow video with on-screen text explaining insurer solvency, plus an SRT subtitle file.

## Quick start

```bash
cd /workspace/insurer-solvency-video
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python build.py
```

Outputs:
- `insurer-solvency-1080p.mp4`
- `insurer-solvency.srt`

## Customize
- Edit `script.yaml` to change slides, durations, colors, and typography.
- The build script renders images with Pillow and assembles them with MoviePy. If you have system fonts installed (e.g., DejaVu), they will be used automatically; otherwise, it will fall back to a basic font.

## Notes
- The audio track is a soft, low-volume tone generated locally (no network). Remove it by commenting out `set_audio(...)` in `build.py` if you prefer silent video.
- Subtitles are provided as a separate `.srt` file aligned to slide timings.