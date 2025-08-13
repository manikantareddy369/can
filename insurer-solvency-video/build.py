#!/usr/bin/env python3
import os
import sys
import math
import datetime
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any

import yaml
from PIL import Image, ImageDraw, ImageFont
import numpy as np

from moviepy.editor import ImageClip, concatenate_videoclips  # type: ignore
from moviepy.audio.AudioClip import AudioArrayClip  # type: ignore


@dataclass
class VideoSpec:
	width: int
	height: int
	fps: int


@dataclass
class StyleSpec:
	background: Tuple[int, int, int]
	accent: Tuple[int, int, int]
	text: Tuple[int, int, int]
	muted_text: Tuple[int, int, int]
	margin_left: int
	margin_right: int
	margin_top: int
	margin_bottom: int
	title_font_size: int
	bullet_font_size: int


@dataclass
class Slide:
	title: str
	bullets: List[str]
	duration: float


def hex_to_rgb(color: str) -> Tuple[int, int, int]:
	color = color.strip()
	if color.startswith('#'):
		color = color[1:]
	if len(color) != 6:
		raise ValueError(f"Expected #RRGGBB, got: {color}")
	return tuple(int(color[i:i+2], 16) for i in (0, 2, 4))  # type: ignore


def load_yaml_config(path: str) -> Tuple[str, str, str, str, VideoSpec, StyleSpec, List[Slide]]:
	with open(path, 'r', encoding='utf-8') as f:
		cfg = yaml.safe_load(f)

	title = cfg.get('title', 'Insurer Solvency')
	subtitle = cfg.get('subtitle', '')
	author = cfg.get('author', '')
	created = cfg.get('created', datetime.date.today().isoformat())

	video_cfg = cfg.get('video', {})
	video = VideoSpec(
		width=int(video_cfg.get('width', 1920)),
		height=int(video_cfg.get('height', 1080)),
		fps=int(video_cfg.get('fps', 30)),
	)

	style_cfg = cfg.get('style', {})
	palette = style_cfg.get('palette', {})
	margins = style_cfg.get('margins', {})
	style = StyleSpec(
		background=hex_to_rgb(palette.get('background', '#0D1B2A')),
		accent=hex_to_rgb(palette.get('accent', '#00C2FF')),
		text=hex_to_rgb(palette.get('text', '#E0E6ED')),
		muted_text=hex_to_rgb(palette.get('muted_text', '#B9C4CF')),
		margin_left=int(margins.get('left', 140)),
		margin_right=int(margins.get('right', 140)),
		margin_top=int(margins.get('top', 160)),
		margin_bottom=int(margins.get('bottom', 120)),
		title_font_size=int(style_cfg.get('title_font_size', 72)),
		bullet_font_size=int(style_cfg.get('bullet_font_size', 44)),
	)

	slides_cfg = cfg.get('slides', [])
	slides: List[Slide] = []
	for s in slides_cfg:
		bullets = [str(b) for b in s.get('bullets', [])]
		slides.append(Slide(title=str(s.get('title', '')), bullets=bullets, duration=float(s.get('duration', 8))))

	return title, subtitle, author, created, video, style, slides


def find_font(preferred: List[str]) -> Optional[str]:
	candidates = []
	font_dirs = [
		"/usr/share/fonts/truetype",
		"/usr/share/fonts",
		"/usr/local/share/fonts",
		os.path.expanduser("~/.local/share/fonts"),
		os.path.expanduser("~/.fonts"),
	]
	for base in font_dirs:
		for root, _dirs, files in os.walk(base):
			for filename in files:
				lower = filename.lower()
				for p in preferred:
					if p.lower() in lower and (lower.endswith('.ttf') or lower.endswith('.otf')):
						candidates.append(os.path.join(root, filename))
	if candidates:
		# Prefer shorter path (often the "main" file), then lexicographic
		candidates.sort(key=lambda p: (len(p), p))
		return candidates[0]
	return None


def load_fonts(title_size: int, bullet_size: int) -> Tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
	preferred_title = ["DejaVuSans-Bold", "Inter-Bold", "Arial-Bold", "LiberationSans-Bold", "NotoSans-Bold"]
	preferred_text = ["DejaVuSans", "Inter", "Arial", "LiberationSans", "NotoSans"]

	title_path = find_font(preferred_title) or find_font([p.replace('-Bold', '') for p in preferred_title])
	text_path = find_font(preferred_text)

	if title_path and text_path:
		return ImageFont.truetype(title_path, title_size), ImageFont.truetype(text_path, bullet_size)
	# Fallback to default PIL bitmap font
	return ImageFont.load_default(), ImageFont.load_default()


def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
	bbox = draw.textbbox((0, 0), text, font=font)
	w = max(0, bbox[2] - bbox[0])
	h = max(0, bbox[3] - bbox[1])
	return w, h


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
	words = text.strip().split()
	if not words:
		return []
	lines: List[str] = []
	current: List[str] = []
	for word in words:
		trial = (" ".join(current + [word])).strip()
		w, _ = measure_text(draw, trial, font)
		if w <= max_width or not current:
			current.append(word)
		else:
			lines.append(" ".join(current))
			current = [word]
	if current:
		lines.append(" ".join(current))
	return lines


def draw_slide_image(index: int, slide: Slide, video: VideoSpec, style: StyleSpec, title_font: ImageFont.ImageFont, bullet_font: ImageFont.ImageFont) -> Image.Image:
	img = Image.new('RGB', (video.width, video.height), color=style.background)
	draw = ImageDraw.Draw(img)

	left = style.margin_left
	right = video.width - style.margin_right
	top = style.margin_top
	bottom = video.height - style.margin_bottom
	content_width = max(0, right - left)

	# Accent line under title area
	accent_y = top - int(style.title_font_size * 0.5)
	accent_h = max(6, int(style.title_font_size * 0.08))
	draw.rectangle([(left, accent_y), (right, accent_y + accent_h)], fill=style.accent)

	# Title
	title_text = slide.title
	title_color = style.text
	title_w, title_h = measure_text(draw, title_text, title_font)
	draw.text((left, top - title_h - int(style.title_font_size * 0.2)), title_text, font=title_font, fill=title_color)

	# Bullets
	bullet_color = style.text
	bullet_leading = int(style.bullet_font_size * 1.35)
	bullet_gap = int(style.bullet_font_size * 0.65)
	bullet_x = left
	current_y = top + int(style.title_font_size * 0.2)

	for bullet in slide.bullets:
		wrapped = wrap_lines(draw, bullet, bullet_font, content_width - 60)
		first_line = True
		for line in wrapped:
			prefix = "•  " if first_line else "   "
			first_line = False
			text = prefix + line
			draw.text((bullet_x, current_y), text, font=bullet_font, fill=bullet_color)
			current_y += bullet_leading
		current_y += bullet_gap

	return img


def ensure_dir(path: str) -> None:
	os.makedirs(path, exist_ok=True)


def seconds_to_srt_time(seconds: float) -> str:
	ms_total = int(round(seconds * 1000))
	h = ms_total // 3_600_000
	ms_total -= h * 3_600_000
	m = ms_total // 60_000
	ms_total -= m * 60_000
	s = ms_total // 1000
	ms = ms_total - s * 1000
	return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(slides: List[Slide], out_path: str) -> None:
	with open(out_path, 'w', encoding='utf-8') as f:
		cursor = 0.0
		for i, s in enumerate(slides, start=1):
			start = seconds_to_srt_time(cursor)
			end = seconds_to_srt_time(cursor + s.duration)
			f.write(f"{i}\n")
			f.write(f"{start} --> {end}\n")
			f.write(s.title.strip() + "\n")
			for b in s.bullets:
				f.write("- " + b.strip() + "\n")
			f.write("\n")
			cursor += s.duration


def build_audio_track(total_duration: float, sample_rate: int = 44100) -> AudioArrayClip:
	# Gentle evolving sine blend with fade in/out, very low volume
	t = np.linspace(0, total_duration, int(total_duration * sample_rate), endpoint=False, dtype=np.float64)
	base = 220.0
	lfo = 0.5 * np.sin(2 * np.pi * 0.07 * t) + 0.5 * np.sin(2 * np.pi * 0.11 * t + 1.3)
	freq = base * (1.0 + 0.02 * lfo)
	phase = 2 * np.pi * np.cumsum(freq) / sample_rate
	signal = np.sin(phase)
	# Add a soft second harmonic
	signal += 0.25 * np.sin(2 * phase + 0.2)
	# Envelope
	fade_in = np.minimum(1.0, t / 1.0)
	fade_out = np.minimum(1.0, (total_duration - t) / 1.0)
	env = np.minimum(fade_in, fade_out)
	signal = signal * env * 0.04  # very low volume
	arr = signal.astype(np.float32).reshape((-1, 1))
	return AudioArrayClip(arr, fps=sample_rate)


def main() -> None:
	project_dir = os.path.dirname(os.path.abspath(__file__))
	cfg_path = os.path.join(project_dir, 'script.yaml')
	build_dir = os.path.join(project_dir, 'build')
	slides_dir = os.path.join(build_dir, 'slides')
	output_video = os.path.join(project_dir, 'insurer-solvency-1080p.mp4')
	output_srt = os.path.join(project_dir, 'insurer-solvency.srt')

	print("[1/6] Loading configuration ...")
	title, subtitle, author, created, video, style, slides = load_yaml_config(cfg_path)

	print("[2/6] Preparing directories ...")
	ensure_dir(build_dir)
	ensure_dir(slides_dir)

	print("[3/6] Selecting fonts ...")
	title_font, bullet_font = load_fonts(style.title_font_size, style.bullet_font_size)
	if isinstance(title_font, ImageFont.ImageFont) and title_font == ImageFont.load_default():
		print("Warning: Using default PIL bitmap font. Install system fonts for better output.")

	print("[4/6] Rendering slides ...")
	image_paths: List[str] = []
	for idx, s in enumerate(slides):
		img = draw_slide_image(idx, s, video, style, title_font, bullet_font)
		filename = os.path.join(slides_dir, f"slide_{idx:02d}.png")
		img.save(filename, format='PNG')
		image_paths.append(filename)

	print("[5/6] Building video timeline ...")
	clips: List[ImageClip] = []
	for path, s in zip(image_paths, slides):
		clip = ImageClip(path).set_duration(max(0.1, float(s.duration)))
		# Light fade at boundaries for polish
		try:
			clip = clip.fadein(0.25).fadeout(0.25)
		except Exception:
			pass
		clips.append(clip)
	final = concatenate_videoclips(clips, method='compose')

	total_duration = sum(max(0.1, float(s.duration)) for s in slides)
	audio = build_audio_track(total_duration)
	final = final.set_audio(audio)

	print("[6/6] Writing output ... this can take a minute")
	final.write_videofile(
		output_video,
		fps=video.fps,
		codec='libx264',
		preset='medium',
		bitrate='3000k',
		audio_codec='aac',
		audio_bitrate='128k',
		threads=os.cpu_count() or 2,
		verbose=False,
		logger=None,
	)

	write_srt(slides, output_srt)
	print(f"Done.\nVideo: {output_video}\nSubtitles: {output_srt}")


if __name__ == '__main__':
	try:
		main()
	except KeyboardInterrupt:
		print("Interrupted.")
		sys.exit(130)
	except Exception as exc:
		print(f"Build failed: {exc}")
		sys.exit(1)