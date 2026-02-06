from ytdl.cli import choose_caption_lang


def test_choose_caption_lang_prefers_english_manual():
    info = {
        "subtitles": {"en": [{"ext": "vtt"}]},
        "automatic_captions": {"es": [{"ext": "vtt"}]},
        "language": "es",
    }
    assert choose_caption_lang(info) == "en"


def test_choose_caption_lang_prefers_english_variant():
    info = {
        "subtitles": {"en-GB": [{"ext": "vtt"}]},
        "automatic_captions": {},
        "language": "fr",
    }
    assert choose_caption_lang(info) == "en-GB"


def test_choose_caption_lang_fallback_to_primary_language():
    info = {
        "subtitles": {"fr": [{"ext": "vtt"}]},
        "automatic_captions": {"de": [{"ext": "vtt"}]},
        "language": "fr",
    }
    assert choose_caption_lang(info) == "fr"


def test_choose_caption_lang_none_when_no_captions():
    assert choose_caption_lang({"subtitles": {}, "automatic_captions": {}}) is None
