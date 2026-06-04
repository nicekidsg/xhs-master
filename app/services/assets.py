from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont

from app.config import settings


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], font, fill, width: int, line_gap: int = 12) -> int:
    x, y = xy
    lines: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line:
            lines.append("")
            continue
        lines.extend(wrap(raw_line, width=width))
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + line_gap
    return y


def generate_assets(draft: dict, base_dir: Path | None = None) -> list[dict[str, str]]:
    output_root = base_dir or settings.asset_dir
    draft_dir = output_root / f"draft-{draft['id']}"
    draft_dir.mkdir(parents=True, exist_ok=True)

    cover_path = draft_dir / "cover-3x4.png"
    body_path = draft_dir / "body-card-3x4.png"
    frames_dir = draft_dir / "video-frames"
    frames_dir.mkdir(exist_ok=True)

    _make_cover(cover_path, draft)
    _make_body_card(body_path, draft)
    frame_paths = _make_video_frames(frames_dir, draft)
    subtitle_path = _write_srt(draft_dir / "subtitles.srt", draft["video_script"])
    package_path = _write_video_package(draft_dir / "video-package.md", draft, frame_paths, subtitle_path)

    return [
        {"kind": "image", "path": str(cover_path), "description": "3:4 图文封面"},
        {"kind": "image", "path": str(body_path), "description": "3:4 正文配图"},
        {"kind": "video_package", "path": str(package_path), "description": "9:16 短视频分镜、字幕与渲染包"},
    ]


def _make_cover(path: Path, draft: dict) -> None:
    image = Image.new("RGB", (1080, 1440), "#f7f3eb")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1080, 160), fill="#111827")
    draw.text((64, 52), "AI/效率工具", font=_font(42), fill="#f9fafb")
    draw.rounded_rectangle((64, 260, 1016, 1050), radius=24, fill="#ffffff", outline="#d6d3d1", width=2)
    _draw_wrapped(draw, draft["cover_text"], (112, 360), _font(92), "#111827", width=12, line_gap=24)
    draw.text((112, 928), "今天就能跑通的工作流", font=_font(44), fill="#be123c")
    draw.text((64, 1310), "#AI工具 #效率工具 #小红书起号", font=_font(38), fill="#374151")
    image.save(path)


def _make_body_card(path: Path, draft: dict) -> None:
    image = Image.new("RGB", (1080, 1440), "#eef2f7")
    draw = ImageDraw.Draw(image)
    draw.text((72, 70), "发布前检查清单", font=_font(64), fill="#111827")
    checklist = "\n".join(f"- {note}" for note in draft["risk_notes"])
    _draw_wrapped(draw, checklist, (88, 210), _font(44), "#1f2937", width=22, line_gap=18)
    draw.rounded_rectangle((72, 930, 1008, 1240), radius=20, fill="#ffffff", outline="#cbd5e1", width=2)
    _draw_wrapped(draw, draft["cta"], (112, 990), _font(48), "#111827", width=19, line_gap=16)
    draw.text((72, 1320), "定位：AI/效率工具 | 节奏：每日 20:30", font=_font(34), fill="#475569")
    image.save(path)


def _make_video_frames(frames_dir: Path, draft: dict) -> list[Path]:
    paths = []
    for item in draft["video_script"]:
        image = Image.new("RGB", (1080, 1920), "#111827")
        draw = ImageDraw.Draw(image)
        draw.text((72, 80), f"Scene {item['scene']}", font=_font(48), fill="#f43f5e")
        _draw_wrapped(draw, item["visual"], (72, 220), _font(72), "#f9fafb", width=12, line_gap=28)
        draw.rounded_rectangle((72, 1320, 1008, 1660), radius=24, fill="#f9fafb")
        _draw_wrapped(draw, item["subtitle"], (112, 1400), _font(64), "#111827", width=14, line_gap=20)
        path = frames_dir / f"scene-{item['scene']:02d}.png"
        image.save(path)
        paths.append(path)
    return paths


def _write_srt(path: Path, script: list[dict]) -> Path:
    lines = []
    start = 0
    for index, item in enumerate(script, start=1):
        end = start + 5
        lines.append(str(index))
        lines.append(f"00:00:{start:02d},000 --> 00:00:{end:02d},000")
        lines.append(item["subtitle"])
        lines.append("")
        start = end
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_video_package(path: Path, draft: dict, frames: list[Path], subtitle_path: Path) -> Path:
    frame_lines = "\n".join(f"- {frame.name}" for frame in frames)
    voiceover = "\n".join(f"{item['scene']}. {item['voiceover']}" for item in draft["video_script"])
    path.write_text(
        (
            f"# {draft['selected_title']} 短视频发布包\n\n"
            "规格：9:16 竖屏，建议每个分镜 5 秒。\n\n"
            f"## 分镜帧\n{frame_lines}\n\n"
            f"## 字幕\n{subtitle_path.name}\n\n"
            f"## 旁白\n{voiceover}\n\n"
            "环境安装 ffmpeg 后，可将分镜帧、旁白音频和字幕合成为 MP4。"
        ),
        encoding="utf-8",
    )
    return path

