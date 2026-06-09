"""Custom Jinja2 filters for safe HTML rendering."""

from markupsafe import Markup, escape


def highlight(text: str) -> Markup:
    """HTML-escape text, then unescape only <mark> tags from FTS5 snippets.

    Safe: script/iframe/img tags in article content are escaped.
    """
    if not text:
        return Markup("")
    # str() avoids Markup.replace re-escaping the <mark> tags
    escaped = str(escape(text))
    result = escaped.replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")
    return Markup(result)


def nl2br(text: str) -> Markup:
    """HTML-escape text, then convert newlines to <br> tags.

    Safe: any HTML in the input is escaped.
    """
    if not text:
        return Markup("")
    # str() avoids Markup.replace re-escaping the <br> tags
    escaped = str(escape(text))
    return Markup(escaped.replace("\n", "<br>\n"))
