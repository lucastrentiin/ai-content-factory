from app.integrations.trends.sources import _traffic, parse_google_trends_rss, parse_news_rss
from app.services.trends import normalize_key

TRENDS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>Final do campeonato</title><ht:approx_traffic>200K+</ht:approx_traffic><pubDate>Sat, 15 Nov 2026 10:00:00 +0000</pubDate>
<ht:news_item><ht:news_item_title>Time vence</ht:news_item_title><ht:news_item_url>https://exemplo.com/a</ht:news_item_url>
<ht:news_item_source>Fonte</ht:news_item_source></ht:news_item></item>
<item><title>Eclipse</title><ht:approx_traffic>5000+</ht:approx_traffic></item>
</channel></rss>"""

NEWS_XML = """<rss><channel><item><title>Notícia importante - Jornal X</title><link>https://n.com/1</link>
<source>Jornal X</source></item></channel></rss>"""


def test_google_trends_rss_parser():
    items = parse_google_trends_rss(TRENDS_XML)
    assert [i.name for i in items] == ["Final do campeonato", "Eclipse"]
    assert items[0].popularity == 200_000 and items[0].url == "https://exemplo.com/a" and items[0].rank == 1
    assert items[1].popularity == 5000


def test_news_parser_strips_source():
    items = parse_news_rss(NEWS_XML)
    assert items[0].name == "Notícia importante" and items[0].url == "https://n.com/1"


def test_helpers():
    assert _traffic("1M+") == 1_000_000 and _traffic(None) == 0
    assert normalize_key("  Ação  Épica!! ") == "acao epica"
