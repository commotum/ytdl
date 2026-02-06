from pathlib import Path

from ytdl.cli import build_extract_opus_cmd


def test_build_extract_opus_cmd():
    cmd = build_extract_opus_cmd(Path("in.mp4"), Path("out.opus"), bitrate="64k")
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert "libopus" in cmd
    assert "64k" in cmd
    assert cmd[-1] == "out.opus"
