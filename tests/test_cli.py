from ytdl.cli import build_download_cmd


def test_build_download_cmd_basic():
    cmd = build_download_cmd("https://example.com/video")
    # Should include output template flags and url at end
    assert "-o" in cmd
    assert cmd[-1] == "https://example.com/video"
    # Prefer mp4 format + merge
    assert "--merge-output-format" in cmd
    assert "mp4" in cmd
    # Pipeline-stability flags
    assert "--restrict-filenames" in cmd
    assert "--write-info-json" in cmd


def test_build_download_cmd_audio_only():
    cmd = build_download_cmd("u", audio_only=True)
    assert "-x" in cmd
    assert "bestaudio/best" in cmd


def test_build_download_cmd_no_playlist():
    cmd = build_download_cmd("u", playlist=False)
    assert "--no-playlist" in cmd
