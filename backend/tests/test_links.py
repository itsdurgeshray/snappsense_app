import pytest

from app.links import LinkError, parse_link


@pytest.mark.parametrize(
    "raw,store,app_id,country",
    [
        ("https://play.google.com/store/apps/details?id=com.flipkart.android", "play", "com.flipkart.android", "us"),
        ("play.google.com/store/apps/details?id=com.whatsapp&hl=en&gl=IN", "play", "com.whatsapp", "in"),
        ("com.spotify.music", "play", "com.spotify.music", "us"),
        ("https://apps.apple.com/gb/app/spotify-music-and-podcasts/id324684580", "app", "324684580", "gb"),
        ("https://apps.apple.com/app/id310633997", "app", "310633997", "us"),
        ("https://itunes.apple.com/us/app/whatsapp/id310633997?mt=8", "app", "310633997", "us"),
        ("id324684580", "app", "324684580", "us"),
        ("324684580", "app", "324684580", "us"),
    ],
)
def test_parse(raw, store, app_id, country):
    ref = parse_link(raw)
    assert (ref.store, ref.app_id, ref.country) == (store, app_id, country)


def test_country_override():
    assert parse_link("https://apps.apple.com/us/app/id324684580", country="IN").country == "in"


@pytest.mark.parametrize("raw", ["", "hello world", "https://example.com/app?id=com.x.y", "https://play.google.com/store/apps/details", "https://apps.apple.com/us/app/spotify"])
def test_rejects(raw):
    with pytest.raises(LinkError):
        parse_link(raw)
