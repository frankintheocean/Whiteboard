"""🛡️ Filter unsafe content from rich notes."""
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit


class _RichTextFilter(HTMLParser):
    blocked = {"script", "style", "iframe", "object", "embed"}
    allowed = {"html", "head", "body", "meta", "p", "br", "span", "b", "strong",
               "i", "em", "u", "s", "a", "img", "div", "ul", "ol", "li",
               "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr", "td", "th",
               "thead", "tbody", "hr", "pre", "blockquote", "font", "sub", "sup"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.depth += 1
            return
        if self.depth or tag not in self.allowed:
            return
        kept = []
        for name, value in attrs:
            value = value or ""
            if name == "href":
                try:
                    if urlsplit(value).scheme.lower() not in ("https", "http", "mailto"):
                        continue
                except ValueError:
                    continue
            elif name == "src":
                # Retain images already embedded by older versions.
                if not value.lower().startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/gif;base64,")):
                    continue
            elif name == "style":
                if any(x in value.lower() for x in ("url(", "expression", "@import")):
                    continue
            elif name not in ("align", "color", "face", "size", "width", "height", "colspan", "rowspan", "type", "content", "name"):
                continue
            kept.append(f' {name}="{escape(value, quote=True)}"')
        self.output.append(f"<{tag}{''.join(kept)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.blocked:
            self.depth = max(0, self.depth - 1)
        elif not self.depth and tag in self.allowed:
            self.output.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.depth:
            self.output.append(escape(data))


def safe_rich_text(value):
    parser = _RichTextFilter()
    parser.feed(value)
    parser.close()
    return "".join(parser.output)
