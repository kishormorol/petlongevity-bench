#!/usr/bin/env python3
"""Build a silent, visual practice walkthrough for the clinician portal."""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SLIDES = [
    ("Practice annotation walkthrough", ["A 48-second guide to record ONE finding from ONE paper.", "This is a practice draft only — not clinical advice and not benchmark gold data."]),
    ("1. Choose one paper", ["Enter your reviewer ID.", "Then choose a single paper from the left-hand list."]),
    ("2. Find one factual result", ["Read until you find one result worth recording.", "Do not give treatment advice or diagnose an animal."]),
    ("3. Write one short claim", ["In the right-hand form, write one small statement about that result.", "Keep it limited to this paper, this species, and this outcome."]),
    ("4. Capture the proof", ["Highlight the exact sentence or table row that proves the claim.", "Click “Capture this evidence.” The evidence location is recorded automatically."]),
    ("5. Choose the simple answers", ["Choose the paper section, judgment, study type, outcome, and conclusion.", "If the paper cannot answer the claim, choose “Not enough information.”"]),
    ("6. Follow the checklist", ["The green checklist names anything still missing.", "When it says “Ready to save this finding,” click “Save this annotation.”"]),
    ("7. Download when finished", ["Repeat for the next finding.", "At the end, click “Download my completed annotations” and return the JSONL file to the coordinator."]),
]


def _slide(title: str, lines: list[str]) -> Image.Image:
    """Render one 1280x720 tutorial card using local system fonts."""
    regular = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 31)
    header = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 29)
    title_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 45)
    note = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 19)
    canvas = Image.new("RGB", (1280, 720), "#092c48")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((55, 55, 1225, 665), radius=16, fill="white")
    draw.rounded_rectangle((55, 55, 1225, 147), radius=16, fill="#087d75")
    draw.rectangle((55, 131, 1225, 147), fill="#087d75")
    draw.text((96, 84), "PetLongevity-Bench · clinician practice walkthrough", font=header, fill="white")
    draw.text((120, 215), title, font=title_font, fill="#092c48")
    for position, line in enumerate(lines):
        draw.text((120, 305 + position * 64), line, font=regular, fill="#173f48")
    draw.rounded_rectangle((105, 575, 1175, 629), radius=9, fill="#e8f6f2")
    draw.text((130, 593), "Record what the paper says. Do not diagnose, prescribe, or create benchmark gold data.", font=note, fill="#20685f")
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="leaderboard/review/annotation_walkthrough.mp4")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="petbench_walkthrough_") as directory:
        root = Path(directory)
        inputs: list[str] = []
        filter_inputs: list[str] = []
        for index, (title, lines) in enumerate(SLIDES):
            png = root / f"{index:02d}.png"
            _slide(title, lines).save(png)
            inputs.extend(["-loop", "1", "-framerate", "30", "-t", "6", "-i", str(png)])
            filter_inputs.append(f"[{index}:v]")
        command = [
            "ffmpeg", "-y", *inputs, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-filter_complex", f"{''.join(filter_inputs)}concat=n={len(SLIDES)}:v=1:a=0[video]",
            "-map", "[video]", "-map", f"{len(SLIDES)}:a", "-shortest", "-c:v", "libx264", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(output),
        ]
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
