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

app = typer.Typer(add_completion=False, no_args_is_help=True)


DEFAULT_OUTDIR = Path("Downloads")
DEFAULT_OUTTMPL = str(DEFAULT_OUTDIR / "%(title)s [%(id)s].%(ext)s")


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
        "-o",
        outtmpl,
    ]

    if not playlist:
        cmd.append("--no-playlist")

    if audio_only:
        # Default to best audio; keep it simple and let yt-dlp/ffmpeg decide container.
        cmd += ["-f", "bestaudio/best", "-x"]

    if extra:
        cmd += extra

    cmd.append(url)
    return cmd


def build_info_cmd(url: str) -> list[str]:
    return [*_yt_dlp_exe(), "-J", url]


def run(cmd: list[str], *, verbose: bool = False) -> RunResult:
    if verbose:
        typer.echo("$ " + " ".join(shlex.quote(c) for c in cmd), err=True)

    p = subprocess.run(cmd)
    return RunResult(cmd=cmd, returncode=p.returncode)


@app.command()
def dl(
    url: str = typer.Argument(..., help="YouTube (or other supported site) URL."),
    outdir: Path = typer.Option(DEFAULT_OUTDIR, "--outdir", help="Output directory."),
    playlist: bool = typer.Option(True, "--playlist/--no-playlist", help="Download playlist items if URL is a playlist."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print the executed command."),
):
    """Download best video+audio for a URL."""
    _ensure_outdir(outdir)
    outtmpl = str(outdir / Path(DEFAULT_OUTTMPL).name)
    cmd = build_download_cmd(url, outtmpl=outtmpl, playlist=playlist)
    r = run(cmd, verbose=verbose)
    raise typer.Exit(r.returncode)


@app.command()
def audio(
    url: str = typer.Argument(..., help="YouTube (or other supported site) URL."),
    outdir: Path = typer.Option(DEFAULT_OUTDIR, "--outdir", help="Output directory."),
    playlist: bool = typer.Option(True, "--playlist/--no-playlist", help="Download playlist items if URL is a playlist."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print the executed command."),
):
    """Download audio-only for a URL."""
    _ensure_outdir(outdir)
    outtmpl = str(outdir / Path(DEFAULT_OUTTMPL).name)
    cmd = build_download_cmd(url, outtmpl=outtmpl, audio_only=True, playlist=playlist)
    r = run(cmd, verbose=verbose)
    raise typer.Exit(r.returncode)


@app.command()
def info(
    url: str = typer.Argument(..., help="YouTube (or other supported site) URL."),
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
