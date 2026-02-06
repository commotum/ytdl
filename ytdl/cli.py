from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import typer

from . import doctor

app = typer.Typer(add_completion=False, no_args_is_help=True)


DEFAULT_OUTDIR = Path("Downloads")
# Prefer ID-based filenames for robust downstream pipelines (no Unicode/quote surprises).
# The human-readable title can always be recovered from the .info.json sidecar.
DEFAULT_OUTTMPL = str(DEFAULT_OUTDIR / "%(id)s.%(ext)s")


@dataclass(frozen=True)
class RunResult:
    cmd: list[str]
    returncode: int


def _ensure_outdir(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)


def _yt_dlp_exe() -> list[str]:
    """Prefer the venv-installed yt-dlp, falling back to python -m yt_dlp."""
    exe = Path(sys.executable).resolve().parent / "yt-dlp"
    if exe.exists():
        return [str(exe)]
    return [sys.executable, "-m", "yt_dlp"]


VIDEO_FMT_MP4 = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"


def build_download_cmd(
    url: str,
    *,
    outtmpl: str = DEFAULT_OUTTMPL,
    audio_only: bool = False,
    playlist: bool = True,
    extra: Optional[list[str]] = None,
) -> list[str]:
    cmd = [
        *_yt_dlp_exe(),
        "--no-progress",
        "--newline",
        # Make filenames safe/portable even if a caller overrides outtmpl.
        "--restrict-filenames",
        # Write metadata sidecar so title/uploader/etc are preserved even with ID filenames.
        "--write-info-json",
        "-o",
        outtmpl,
    ]

    if not playlist:
        cmd.append("--no-playlist")

    if audio_only:
        # Default to best audio; keep it simple and let yt-dlp/ffmpeg decide container.
        cmd += ["-f", "bestaudio/best", "-x"]
    else:
        # Prefer mp4 for interoperability.
        cmd += ["-f", VIDEO_FMT_MP4, "--merge-output-format", "mp4"]

    if extra:
        cmd += extra

    cmd.append(url)
    return cmd


def build_info_cmd(url: str) -> list[str]:
    return [*_yt_dlp_exe(), "-J", url]


def build_extract_opus_cmd(src: Path, dest: Path, *, bitrate: str = "96k") -> list[str]:
    """Build an ffmpeg command that extracts/encodes audio to Opus.

    We intentionally re-encode to Opus to produce a stable `.opus` artifact even
    when the source container uses AAC (common for mp4).
    """
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-c:a",
        "libopus",
        "-b:a",
        bitrate,
        str(dest),
    ]


def _available_caption_langs(info: dict) -> set[str]:
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    langs = set(subs.keys()) | set(auto.keys())
    # yt-dlp can include pseudo keys like "live_chat"; keep them out.
    return {lang for lang in langs if isinstance(lang, str) and lang and lang != "live_chat"}


def choose_caption_lang(info: dict) -> Optional[str]:
    """Choose one caption language.

    Policy:
    1) Prefer best available English captions (manual or auto): any lang that starts with "en".
    2) Else fall back to the video's primary/source language (as reported by yt-dlp),
       *only if* captions exist for it.
    3) Else return None (skip).
    """

    langs = _available_caption_langs(info)
    if not langs:
        return None

    # Prefer English (en, en-US, en-GB, en.*)
    en_like = sorted(
        [
            lang
            for lang in langs
            if lang == "en" or lang.startswith("en-") or lang.startswith("en_") or lang.startswith("en")
        ]
    )
    if en_like:
        # Prefer plain "en" if present; otherwise deterministic first.
        return "en" if "en" in en_like else en_like[0]

    # Fall back to detected/original language if present in captions.
    for key in ("original_language", "language"):
        v = info.get(key)
        if isinstance(v, str) and v in langs:
            return v

    return None


def build_captions_cmd(url: str, *, outtmpl: str, lang: str) -> list[str]:
    """Download best available captions in a single language (manual or auto).

    Outputs .vtt when available; if none available, yt-dlp exits 0 but creates nothing.
    """
    return [
        *_yt_dlp_exe(),
        "--no-progress",
        "--newline",
        "--restrict-filenames",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        lang,
        "--sub-format",
        "vtt",
        "-o",
        outtmpl,
        "--no-playlist",
        url,
    ]


def run(cmd: list[str], *, verbose: bool = False) -> RunResult:
    if verbose:
        typer.echo("$ " + " ".join(shlex.quote(c) for c in cmd), err=True)

    p = subprocess.run(cmd)
    return RunResult(cmd=cmd, returncode=p.returncode)


def _print_download_summary_json(*, url: str, outdir: Path, exit_code: int) -> None:
    """Emit a conservative JSON summary for chaining.

    We intentionally do not try to perfectly enumerate output files (yt-dlp has
    many modes and templates). For chaining, outdir + url + exit_code is still
    useful, and can be extended later.
    """
    payload = {
        "url": url,
        "outdir": str(outdir),
        "exit_code": exit_code,
    }
    sys.stdout.write(json.dumps(payload) + "\n")


@app.command()
def get(
    url: str = typer.Argument(..., help="Video URL (YouTube or any yt-dlp supported site)."),
    outdir: Path = typer.Option(DEFAULT_OUTDIR, "--outdir", help="Output directory."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print the executed command."),
    json_out: bool = typer.Option(False, "--json", help="Print a JSON summary to stdout (for scripting)."),
):
    """Safe default: download a single video (no playlist) as best video+audio."""
    _ensure_outdir(outdir)
    outtmpl = str(outdir / Path(DEFAULT_OUTTMPL).name)
    cmd = build_download_cmd(url, outtmpl=outtmpl, playlist=False)
    r = run(cmd, verbose=verbose)
    if json_out:
        _print_download_summary_json(url=url, outdir=outdir, exit_code=r.returncode)
    raise typer.Exit(r.returncode)


@app.command()
def dl(
    url: str = typer.Argument(..., help="Video URL (YouTube or any yt-dlp supported site)."),
    outdir: Path = typer.Option(DEFAULT_OUTDIR, "--outdir", help="Output directory."),
    playlist: bool = typer.Option(True, "--playlist/--no-playlist", help="Download playlist items if URL is a playlist."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print the executed command."),
    json_out: bool = typer.Option(False, "--json", help="Print a JSON summary to stdout (for scripting)."),
):
    """Download best video+audio for a URL."""
    _ensure_outdir(outdir)
    outtmpl = str(outdir / Path(DEFAULT_OUTTMPL).name)
    cmd = build_download_cmd(url, outtmpl=outtmpl, playlist=playlist)
    r = run(cmd, verbose=verbose)
    if json_out:
        _print_download_summary_json(url=url, outdir=outdir, exit_code=r.returncode)
    raise typer.Exit(r.returncode)


@app.command()
def audio(
    url: str = typer.Argument(..., help="Video URL (YouTube or any yt-dlp supported site)."),
    outdir: Path = typer.Option(DEFAULT_OUTDIR, "--outdir", help="Output directory."),
    playlist: bool = typer.Option(True, "--playlist/--no-playlist", help="Download playlist items if URL is a playlist."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print the executed command."),
    json_out: bool = typer.Option(False, "--json", help="Print a JSON summary to stdout (for scripting)."),
):
    """Download audio-only for a URL."""
    _ensure_outdir(outdir)
    outtmpl = str(outdir / Path(DEFAULT_OUTTMPL).name)
    cmd = build_download_cmd(url, outtmpl=outtmpl, audio_only=True, playlist=playlist)
    r = run(cmd, verbose=verbose)
    if json_out:
        _print_download_summary_json(url=url, outdir=outdir, exit_code=r.returncode)
    raise typer.Exit(r.returncode)


@app.command()
def pair(
    url: str = typer.Argument(..., help="Video URL (YouTube or any yt-dlp supported site)."),
    outdir: Path = typer.Option(DEFAULT_OUTDIR, "--outdir", help="Output directory."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print the executed commands."),
    json_out: bool = typer.Option(False, "--json", help="Print a JSON summary to stdout (for scripting)."),
    opus_bitrate: str = typer.Option("96k", "--opus-bitrate", help="Target Opus bitrate (ffmpeg -b:a)."),
):
    """Download a single MP4 (video+audio) AND an Opus audio file.

    Intended for the common pipeline:
    - save a high-quality, single-file MP4 for viewing/archive
    - save a stable `.opus` for feeding diarization (e.g. whisper-diarization)

    This avoids fragile title-based filenames by using the video ID.
    """
    _ensure_outdir(outdir)

    # Resolve the video ID first so we can use deterministic filenames.
    info_cmd = build_info_cmd(url)
    if verbose:
        typer.echo("$ " + " ".join(shlex.quote(c) for c in info_cmd), err=True)
    p = subprocess.run(info_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr)
        raise typer.Exit(p.returncode)

    try:
        data = json.loads(p.stdout)
    except Exception:
        sys.stderr.write(p.stdout)
        raise typer.Exit(2)

    vid = data.get("id")
    if not vid:
        sys.stderr.write("Could not resolve video id from yt-dlp -J output\n")
        raise typer.Exit(2)

    mp4_path = outdir / f"{vid}.mp4"
    opus_path = outdir / f"{vid}.opus"

    # Captions (best English if available, else primary/source language).
    caption_lang = choose_caption_lang(data)

    # Download MP4 (single file).
    mp4_outtmpl = str(outdir / f"{vid}.%(ext)s")
    dl_cmd = build_download_cmd(url, outtmpl=mp4_outtmpl, playlist=False)
    r = run(dl_cmd, verbose=verbose)
    if r.returncode != 0:
        if json_out:
            _print_download_summary_json(url=url, outdir=outdir, exit_code=r.returncode)
        raise typer.Exit(r.returncode)

    # Extract/encode Opus from the MP4.
    extract_cmd = build_extract_opus_cmd(mp4_path, opus_path, bitrate=opus_bitrate)
    rr = run(extract_cmd, verbose=verbose)

    # Captions (best English if available, else primary/source language; else skip).
    caption_files: list[str] = []
    cap_rc = 0
    if caption_lang:
        cap_outtmpl = str(outdir / f"{vid}.%(ext)s")
        cap_cmd = build_captions_cmd(url, outtmpl=cap_outtmpl, lang=caption_lang)
        cap_r = run(cap_cmd, verbose=verbose)
        cap_rc = cap_r.returncode
        # Gather whatever yt-dlp wrote (vtt preferred).
        caption_files = [str(p) for p in sorted(outdir.glob(f"{vid}.*.vtt"))]

    exit_code = 0
    for rc in (rr.returncode, cap_rc):
        if rc != 0:
            exit_code = rc
            break

    if json_out:
        payload = {
            "url": url,
            "outdir": str(outdir),
            "id": vid,
            "mp4": str(mp4_path),
            "opus": str(opus_path),
            "captions_lang": caption_lang,
            "captions": caption_files,
            "exit_code": exit_code,
        }
        sys.stdout.write(json.dumps(payload) + "\n")

    raise typer.Exit(exit_code)


@app.command()
def info(
    url: str = typer.Argument(..., help="Video URL (YouTube or any yt-dlp supported site)."),
    json_out: bool = typer.Option(True, "--json/--no-json", help="Print raw JSON to stdout."),
):
    """Fetch metadata (no download)."""
    cmd = build_info_cmd(url)

    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        # Forward stderr (yt-dlp uses it for diagnostics).
        sys.stderr.write(p.stderr)
        raise typer.Exit(p.returncode)

    if json_out:
        sys.stdout.write(p.stdout)
        return

    # Human-ish summary
    try:
        data = json.loads(p.stdout)
    except Exception:
        sys.stdout.write(p.stdout)
        return

    title = data.get("title")
    vid = data.get("id")
    uploader = data.get("uploader")
    duration = data.get("duration")
    webpage_url = data.get("webpage_url") or url

    parts = [
        f"title: {title}",
        f"id: {vid}",
        f"uploader: {uploader}",
        f"duration_s: {duration}",
        f"url: {webpage_url}",
    ]
    sys.stdout.write("\n".join(parts) + "\n")


@app.command(name="doctor")
def doctor_cmd(
    outdir: Path = typer.Option(DEFAULT_OUTDIR, "--outdir", help="Output directory to validate."),
    json_out: bool = typer.Option(True, "--json/--no-json", help="Output JSON (default) for scripting."),
):
    """Check local dependencies and basic writeability for chaining."""
    report = doctor.check(outdir)
    doctor.print_report(report, json_out=json_out)
    # Non-zero if something important is missing.
    exit_code = 0
    if not report.yt_dlp:
        exit_code = 2
    if not report.outdir_writable:
        exit_code = 3
    raise typer.Exit(exit_code)


@app.command()
def gate():
    """Run fast local checks (ruff + pytest)."""
    env = os.environ.copy()
    # Ensure we use the venv tools if present.
    venv_bin = Path(sys.executable).resolve().parent

    def _run_tool(args: list[str]) -> int:
        cmd = [str(venv_bin / args[0]), *args[1:]]
        # If tool isn't in venv bin (should be), fall back to python -m.
        if not Path(cmd[0]).exists():
            cmd = [sys.executable, "-m", args[0].replace("-", "_"), *args[1:]]
        typer.echo("$ " + " ".join(shlex.quote(c) for c in cmd), err=True)
        return subprocess.run(cmd, env=env).returncode

    rc = _run_tool(["ruff", "check", "."])
    if rc != 0:
        raise typer.Exit(rc)

    rc = _run_tool(["pytest", "-q"])
    raise typer.Exit(rc)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
