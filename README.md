# ytdl

A tiny CLI wrapper around `yt-dlp`, with a stable interface and a local `gate`.

## Install / run (inside repo)

```bash
uv run ytdl --help
```

## Examples

Download best video+audio:

```bash
uv run ytdl dl 'https://www.youtube.com/watch?v=...'
```

Audio-only:

```bash
uv run ytdl audio 'https://www.youtube.com/watch?v=...'
```

Metadata (raw JSON):

```bash
uv run ytdl info --json 'https://www.youtube.com/watch?v=...'
```

Fast local checks:

```bash
uv run ytdl gate
```

## Output directory

By default downloads go to `./Downloads/` inside this repo.

## Notes

- This wraps `yt-dlp` (installed as a Python dependency).
- Some formats require `ffmpeg` to be installed system-wide.
