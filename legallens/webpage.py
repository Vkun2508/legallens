"""Fetch a privacy policy or terms page from a web address (the URL scanner, POST /api/audit-url).

The server does the fetching, so a web address must never reach anything private:

- **Addresses:** only http and https, on the standard ports (80 and 443), with no user name or
  password in the address.
- **SSRF:** every hostname is resolved and every address it resolves to is checked; private,
  loopback, link-local, shared, reserved and multicast addresses are refused, including IPv4
  addresses wrapped in IPv6. The connection then goes to the address that was checked, so a
  second DNS answer can't swap in a private one.
- **Redirects:** at most MAX_REDIRECTS, and each one is checked like the first address.
- **Limits:** TIMEOUT seconds per page in all, at most MAX_BYTES of body, and a User-Agent
  that says what LegalLens is.

A homepage is followed to its privacy policy (or, failing that, its terms) through its links.
Pages that need JavaScript or that block automated visitors get an error that suggests pasting
the text instead. Nothing fetched is logged or stored.
"""

from __future__ import annotations

import codecs
import http.client
import ipaddress
import re
import socket
import ssl
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from legallens.preprocess import normalize_text

MAX_BYTES = 3 * 1024 * 1024
TIMEOUT = 10.0
MAX_REDIRECTS = 4
MAX_URL_CHARS = 2048
USER_AGENT = "Mozilla/5.0 (compatible; LegalLens/2.0; +privacy-policy-checker)"
STANDARD_PORTS = {"http": 80, "https": 443}
MIN_POLICY_WORDS = 120
_JS_ONLY_WORDS = 80

PASTE_INSTEAD = "Open the page, copy the policy text and paste it instead."


class FetchError(Exception):
    """A web address that can't be fetched, with a message the visitor can act on."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class Page:
    url: str  # the final address, after redirects
    kind: str  # "html", "pdf" or "text"
    body: bytes
    charset: str | None = None


@dataclass
class FetchedPolicy:
    url: str  # where the policy was read
    kind: str  # "html", "pdf" or "text"
    title: str = ""
    text: str = ""  # normalized text; empty for a PDF, which the caller extracts from `body`
    body: bytes = b""
    found_from: str | None = None  # the homepage whose link was followed, if any


# --- Addresses -----------------------------------------------------------------------------


def normalize_url(raw: str) -> str:
    """Tidy what a visitor typed: trim it and assume https when no scheme is given."""
    url = raw.strip()
    if not url:
        raise FetchError("Enter the web address of your privacy policy or terms.", 400)
    if len(url) > MAX_URL_CHARS:
        raise FetchError("That web address is too long.", 400)
    if "://" not in url and not url.lower().startswith(("http:", "https:")):
        url = "https://" + url
    return url


def check_url(url: str):
    """Return the split address if its scheme, credentials and port are allowed."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise FetchError("That doesn't look like a web address.", 400) from exc
    scheme = parts.scheme.lower()
    if scheme not in STANDARD_PORTS:
        raise FetchError("Only http and https web addresses can be checked.", 400)
    if not parts.hostname:
        raise FetchError("That doesn't look like a web address.", 400)
    if parts.username is not None or parts.password is not None:
        raise FetchError("Web addresses with a user name or password can't be checked.", 400)
    if not _port_allowed(scheme, port):
        raise FetchError("Only web addresses on the standard ports (80 and 443) can be checked.", 400)
    try:
        parts.hostname.encode("idna")
    except UnicodeError as exc:
        raise FetchError("That doesn't look like a web address.", 400) from exc
    return parts


def _port_allowed(scheme: str, port: int | None) -> bool:
    return port is None or port == STANDARD_PORTS[scheme]


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for globally reachable unicast addresses, unwrapping IPv4 carried in IPv6."""
    if ip.version == 6:
        embedded = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if embedded is None and ip in _NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None and not _is_public(embedded):
            return False
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_PRIVATE_MESSAGE = "That address points to a private or local network, which LegalLens doesn't fetch."


def resolve_public(host: str, port: int) -> list[str]:
    """Resolve `host` and return its addresses, refusing it if any of them isn't public."""
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public(literal):
            raise FetchError(_PRIVATE_MESSAGE, 400)
        return [str(literal)]
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise FetchError("We couldn't find that website. Check the address and try again.") from exc
    addresses = []
    for info in infos:
        address = info[4][0].split("%")[0]  # drop an IPv6 zone id
        if not _is_public(ipaddress.ip_address(address)):
            raise FetchError(_PRIVATE_MESSAGE, 400)
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise FetchError("We couldn't find that website. Check the address and try again.")
    return addresses


# --- HTTP ----------------------------------------------------------------------------------


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """An HTTP connection to an address that was already checked, whatever DNS says next."""

    def __init__(self, host: str, port: int, address: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """As above, with TLS verified against the hostname rather than the address."""

    def __init__(self, host: str, port: int, address: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


@dataclass
class _Response:
    status: int
    headers: dict[str, str]
    body: bytes = b""


def _request(parts, address: str, deadline: float) -> _Response:
    """One GET to a checked address. Reads at most MAX_BYTES of body before the deadline."""
    scheme = parts.scheme.lower()
    port = parts.port or STANDARD_PORTS[scheme]
    remaining = max(0.1, deadline - time.monotonic())
    cls = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    conn = cls(parts.hostname, port, address, remaining)
    path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
    try:
        conn.request("GET", path, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,text/plain;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        })
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        if resp.status in (301, 302, 303, 307, 308) or resp.status >= 400:
            return _Response(resp.status, headers)
        length = headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_BYTES:
            raise FetchError(_too_large(), 413)
        chunks, size = [], 0
        while True:
            if time.monotonic() > deadline:
                raise FetchError("The website took too long to respond. Try again, or paste the text instead.", 504)
            if conn.sock is not None:
                conn.sock.settimeout(max(0.1, deadline - time.monotonic()))
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES:
                raise FetchError(_too_large(), 413)
            chunks.append(chunk)
        return _Response(resp.status, headers, b"".join(chunks))
    except FetchError:
        raise
    except (TimeoutError, socket.timeout) as exc:
        raise FetchError("The website took too long to respond. Try again, or paste the text instead.", 504) from exc
    except ssl.SSLError as exc:
        raise FetchError("The website's security certificate couldn't be verified, so LegalLens didn't read it.") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise FetchError("We couldn't connect to that website. Check the address, or paste the text instead.", 502) from exc
    finally:
        conn.close()


def _too_large() -> str:
    return f"That page is larger than {MAX_BYTES // (1024 * 1024)} MB. {PASTE_INSTEAD}"


def fetch(url: str) -> Page:
    """GET a page, following checked redirects, and say what kind of document it is."""
    deadline = time.monotonic() + TIMEOUT
    for _ in range(MAX_REDIRECTS + 1):
        parts = check_url(url)
        port = parts.port or STANDARD_PORTS[parts.scheme.lower()]
        address = resolve_public(parts.hostname, port)[0]
        resp = _request(parts, address, deadline)
        if resp.status in (301, 302, 303, 307, 308):
            location = resp.headers.get("location")
            if not location:
                raise FetchError("The website sent a redirect without an address.", 502)
            url = urljoin(url, location.strip())
            continue
        break
    else:
        raise FetchError("The website redirected too many times.", 502)

    if resp.status in (401, 403, 429, 451, 503):
        raise FetchError(f"The website didn't let LegalLens read this page; it may block automated visitors. {PASTE_INSTEAD}")
    if resp.status in (404, 410):
        raise FetchError("There's no page at that address. Check the link, or paste the text instead.")
    if resp.status != 200:
        raise FetchError(f"The website returned an error ({resp.status}). Try again later, or paste the text instead.", 502)

    content_type = resp.headers.get("content-type", "").lower()
    media = content_type.split(";")[0].strip()
    match = re.search(r"charset=[\"']?([\w.:-]+)", content_type)
    charset = match.group(1) if match else None
    if media in ("text/html", "application/xhtml+xml") or (not media and resp.body.lstrip()[:1] == b"<"):
        kind = "html"
    elif media == "application/pdf" or resp.body.startswith(b"%PDF-"):
        kind = "pdf"
    elif media in ("text/plain", "text/markdown"):
        kind = "text"
    else:
        raise FetchError("That address isn't a web page or a PDF. Link to the policy page, or paste the text instead.", 415)
    return Page(url, kind, resp.body, charset)


# --- Reading HTML --------------------------------------------------------------------------

# Not part of the policy's text. (Not <head> or <form>: </head> may be omitted, and some
# sites wrap the whole page in a <form>.)
_SKIP = {"script", "style", "noscript", "template", "svg", "math", "nav", "header", "footer",
         "aside", "button", "select", "textarea", "iframe", "canvas", "dialog", "object"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_PARAGRAPHS = {"p", "blockquote", "pre", "address", "table", "dl", "ul", "ol", "figure", "details"}
_LINES = {"div", "section", "article", "main", "li", "tr", "dd", "dt", "br", "hr", "summary", "figcaption", "td", "th"}
_VOID = {"br", "hr", "img", "input", "meta", "link", "source", "wbr", "area", "base", "col", "embed", "track"}


@dataclass
class Document:
    title: str
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (href, link text)
    scripts: int = 0
    challenge: bool = False  # a bot-check page ("Just a moment...")


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []  # the whole body's text
        self.main_parts: list[str] = []  # text inside <main> or <article>
        self.title_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.scripts = 0
        self.skip = 0
        self.main = 0
        self.in_title = False
        self.link: list | None = None  # [href, text parts]

    def _emit(self, text: str) -> None:
        self.parts.append(text)
        if self.main:
            self.main_parts.append(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts += 1
        if tag == "title":
            self.in_title = True
        if tag == "a" and attrs.get("href"):
            self.link = [attrs["href"], [attrs.get("aria-label") or attrs.get("title") or ""]]
        if tag in _SKIP and tag not in _VOID:
            self.skip += 1
            return
        if tag in ("main", "article"):
            self.main += 1
        self._break(tag, start=True)

    def handle_startendtag(self, tag, attrs):
        if tag in ("br", "hr"):
            self._break(tag, start=True)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.link is not None:
            self.links.append((self.link[0], " ".join("".join(self.link[1]).split())))
            self.link = None
        if tag in _SKIP and tag not in _VOID:
            self.skip = max(0, self.skip - 1)
            return
        self._break(tag, start=False)
        if tag in ("main", "article"):
            self.main = max(0, self.main - 1)

    def _break(self, tag: str, start: bool) -> None:
        if self.skip:
            return
        if tag in _HEADINGS or tag in _PARAGRAPHS:
            self._emit("\n\n")
        elif tag == "li" and start:
            self._emit("\n• ")
        elif tag in _LINES:
            self._emit("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self.link is not None:
            self.link[1].append(data)
        if not self.skip and not self.in_title:
            self._emit(data)


def _tidy(parts: list[str]) -> str:
    lines = [" ".join(line.split()) for line in "".join(parts).split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n(?:• ?\n)+", "\n", text)  # empty list items
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return normalize_text(text)


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z]{2,}", text))


def read_html(body: bytes, charset: str | None = None) -> Document:
    """The readable text of a page (its <main> or <article> when that holds the content), its title and links."""
    html = _decode(body, charset)
    reader = _Reader()
    reader.feed(html)
    reader.close()
    title = " ".join("".join(reader.title_parts).split())
    main_text = _tidy(reader.main_parts)
    text = main_text if _word_count(main_text) >= MIN_POLICY_WORDS else _tidy(reader.parts)
    challenge = bool(re.search(r"just a moment|attention required|checking your browser|verify you are human", title, re.I)) or (
        "challenge-platform" in html or "cf-chl-" in html
    )
    return Document(title, text, reader.links, reader.scripts, challenge)


def _decode(body: bytes, charset: str | None) -> str:
    if not charset:
        match = re.search(rb"<meta[^>]+charset=[\"']?([\w.:-]+)", body[:4096], re.I)
        charset = match.group(1).decode("ascii", "ignore") if match else "utf-8"
    try:
        codecs.lookup(charset)
    except LookupError:
        charset = "utf-8"
    return body.decode(charset, errors="replace")


# --- Finding the policy --------------------------------------------------------------------

_POLICY_TERMS = ("personal data", "personal information", "privacy", "consent", "cookie", "data protection",
                 "grievance", "terms of", "terms and conditions", "liability", "refund", "governing law")


def looks_like_policy(text: str) -> bool:
    """A page with enough words and the vocabulary of a privacy policy or terms."""
    lowered = text.lower()
    return _word_count(text) >= MIN_POLICY_WORDS and sum(term in lowered for term in _POLICY_TERMS) >= 2


def find_policy_link(links: list[tuple[str, str]], base_url: str) -> str | None:
    """The page's privacy policy link, or failing that its terms link, as an absolute address."""
    best, best_score = None, 0
    for href, label in links:
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        haystack = f"{label} {href}".lower()
        if re.search(r"privacy|data[ -]?protection|personal[ -]data", haystack):
            score = 3
        elif re.search(r"\bterms\b|terms[-_ ]?(?:of|and|&)|conditions|\btos\b|legal", haystack):
            score = 1
        else:
            continue
        if score > best_score:
            best, best_score = urljoin(base_url, href), score
    if best is not None and urlsplit(best).scheme.lower() not in STANDARD_PORTS:
        return None
    return best


def _is_root(url: str) -> bool:
    return urlsplit(url).path.strip("/") == ""


def _read(page: Page) -> tuple[FetchedPolicy, Document | None]:
    if page.kind == "pdf":
        return FetchedPolicy(page.url, "pdf", body=page.body), None
    if page.kind == "text":
        return FetchedPolicy(page.url, "text", text=normalize_text(_decode(page.body, page.charset))), None
    doc = read_html(page.body, page.charset)
    if doc.challenge:
        raise FetchError(f"The website showed a bot check instead of the page. {PASTE_INSTEAD}")
    return FetchedPolicy(page.url, "html", title=doc.title, text=doc.text), doc


def fetch_policy(raw_url: str) -> FetchedPolicy:
    """Fetch the policy at `raw_url`. A homepage, or a page that isn't a policy, is followed to its policy link."""
    policy, doc = _read(fetch(normalize_url(raw_url)))
    if doc is not None and (_is_root(policy.url) or not looks_like_policy(policy.text)):
        link = find_policy_link(doc.links, policy.url)
        if link and link.split("#")[0] != policy.url.split("#")[0]:
            homepage = policy.url
            policy, doc = _read(fetch(link))
            policy.found_from = homepage
    return _checked(policy, doc)


def _checked(policy: FetchedPolicy, doc: Document | None) -> FetchedPolicy:
    if policy.kind == "pdf":
        return policy
    if doc is not None and doc.scripts and _word_count(policy.text) < _JS_ONLY_WORDS:
        raise FetchError(f"This page builds its text with JavaScript, so LegalLens can't read it. {PASTE_INSTEAD}")
    if not looks_like_policy(policy.text):
        raise FetchError(
            "This page doesn't look like a privacy policy or terms. Link straight to the policy, or paste the text instead."
        )
    return policy


def display_url(url: str) -> str:
    """A short label for a fetched address: host and path, without the scheme."""
    parts = urlsplit(url)
    label = (parts.hostname or "") + (parts.path if parts.path not in ("", "/") else "")
    return label[:120]
