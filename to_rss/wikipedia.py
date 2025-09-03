import logging
from datetime import date, datetime, timedelta

import feedgenerator
import mwcomposerfromhell
import mwparserfromhell
from sentry_sdk import start_span

from to_rss import get_session

logger = logging.getLogger(__name__)

BASE_URL = "https://en.wikipedia.org/wiki/"
# Feed links point at the mobile site, which reads better on phones.
MOBILE_BASE_URL = "https://en.m.wikipedia.org/wiki/"


def get_current_events_by_date(lookup_date: date) -> str:
    # Format the date as a string, this is formatted using the #time extension
    # to Wiki syntax:
    # https://www.mediawiki.org/wiki/Help:Extension:ParserFunctions#.23time with
    # a format of "Y F j". This is awkward because we want the day *not* zero
    # padded, but the month as a string.
    datestr = f"{lookup_date.year} {lookup_date.strftime('%B')} {lookup_date.day}"
    return "Portal:Current_events/" + datestr


def get_article(url: str) -> str:
    """Fetches and returns the article content as a string."""
    response = get_session().get(
        url,
        params={"action": "raw"},
        headers={"User-agent": "to-rssbot (+https://www.to-rss.xyz/)"},
    )
    return response.text


def get_articles() -> str:
    """
    Returns a map of dates to a list of current events on that date.

    The root of this is parsing https://en.wikipedia.org/wiki/Portal:Current_events
    The true information we're after is included via
    https://en.wikipedia.org/wiki/Portal:Current_events/Inclusion
    which then includes the past seven days.
    """
    # Rendered links (the feed's own links and the ones inside each article) use
    # the mobile site. Content is fetched from the desktop site instead: the
    # mobile host 301-redirects ?action=raw to it, so resolving against it would
    # cost an extra round-trip per article.
    resolver = mwcomposerfromhell.ArticleResolver(base_url=MOBILE_BASE_URL)
    fetch_resolver = mwcomposerfromhell.ArticleResolver(base_url=BASE_URL)
    feed = feedgenerator.Rss201rev2Feed(
        "Wikipedia: Portal: Current events",
        resolver.get_article_url(resolver.resolve_article("Portal:Current_events", "")),
        "Wikipedia: Portal: Current events",
    )

    # Start at today.
    day = date.today()

    for i in range(7):
        day -= timedelta(days=1)

        # Create a composer.
        composer = mwcomposerfromhell.WikicodeToHtmlComposer(resolver=resolver)

        # Download the article content.
        article_name = get_current_events_by_date(day)
        url = resolver.get_article_url(resolver.resolve_article(article_name, ""))
        article = get_article(
            fetch_resolver.get_article_url(
                fetch_resolver.resolve_article(article_name, "")
            )
        )
        # Parse the article contents.
        with start_span(op="parse-wikitext", name="Parse " + url):
            wikicode = mwparserfromhell.parse(article)

        with start_span(op="wiki-to-html", name="Convert " + url):
            # Current event pages have a top-level template.
            for template in wikicode.ifilter_templates():
                if template.name == "Current events":
                    content = template.get("content").value

                    try:
                        # Convert the Wikicode to HTML.
                        result = composer.compose(content)
                    except mwcomposerfromhell.HtmlComposingError:
                        logger.error("Unable to render article from: %s", day)
                        continue

                    # Add the results to the RSS feed.
                    feed.add_item(
                        title=f"Current events: {day}",
                        link=url,
                        description=result,
                        pubdate=datetime(*day.timetuple()[:3]),
                    )

                    # Stop processing this article.
                    break

            else:
                logger.error(
                    f"'Current events' template not found in article for {day}"
                )

    if len(feed.items) == 0:
        logger.error("Created empty feed for Wikipedia current events")

    return feed.writeString("utf-8")
