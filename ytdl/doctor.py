from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DoctorReport:
    python: str
    yt_dlp: bool
    ffmpeg: bool
    outdir_writable: bool

    def to_dict(self) -> dict:
        return {
            "python": self.python,
            "yt_dlp": self.yt_dlp,
            "ffmpeg": self.ffmpeg,
            "outdir_writable": self.outdir_writable,
        }


def check(outdir: Path) -> DoctorReport:
    yt_dlp = shutil.which("yt-dlp") is not None
    ffmpeg = shutil.which("ffmpeg") is not None

    outdir_writable = False
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        probe = outdir / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        outdir_writable = True
    except Exception:
        outdir_writable = False

    return DoctorReport(
        python=sys.version.split()[0],
        yt_dlp=yt_dlp,
        ffmpeg=ffmpeg,
        outdir_writable=outdir_writable,
    )


def print_report(report: DoctorReport, *, json_out: bool) -> None:
    if json_out:
        sys.stdout.write(json.dumps(report.to_dict()) + "\n")
        return

    sys.stdout.write("doctor:\n")
    for k, v in report.to_dict().items():
        sys.stdout.write(f"- {k}: {v}\n")
