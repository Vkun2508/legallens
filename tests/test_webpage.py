"""The URL scanner's fetcher: address checks (SSRF), redirects, limits and reading HTML.

No test reaches the internet. DNS is faked with monkeypatch, single requests are faked at
`_request`, and the end-to-end tests talk to a throwaway server on 127.0.0.1, which the
address check has to be told to allow.
"""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from legallens import webpage
from legallens.webpage import FetchError, _Response

POLICY_HTML = (
    "<html><head><title>Privacy policy | Kettle</title></head><body>"
    "<nav><a href='/'>Home</a> <a href='/privacy'>Privacy</a></nav>"
    "<main><h1>Privacy policy</h1>"
    + "".join(
        f"<h2>{i}. Section</h2><p>We collect personal data such as your name and email to deliver orders, "
        "and we ask for your consent before using it for anything else. You can contact our grievance "
        "officer about privacy at any time.</p>"
        for i in range(1, 7)
    )
    + "<ul><li>Access</li><li>Correction</li></ul></main>"
    "<footer><a href='/terms'>Terms</a> <a href='mailto:hi@kettle.example'>Email</a></footer>"
    "<script>track()</script></body></html>"
).encode()

HOME_HTML = (
    b"<html><head><title>Kettle</title></head><body><h1>Dinner, sorted</h1><p>Weekly meal kits.</p>"
    b"<footer><a href='/terms-of-service'>Terms of service</a> <a href='/legal/privacy-policy'>Privacy policy</a>"
    b"</footer></body></html>"
)


def _dns(monkeypatch, table):
    """Fake DNS: hostname -> list of addresses."""

    def fake(host, port, *args, **kwargs):
        if host not in table:
            raise socket.gaierror("not found")
        family = lambda a: socket.AF_INET6 if ":" in a else socket.AF_INET  # noqa: E731
        return [(family(a), socket.SOCK_STREAM, 6, "", (a, port)) for a in table[host]]

    monkeypatch.setattr(webpage.socket, "getaddrinfo", fake)


def _serve(monkeypatch, routes):
    """Fake single requests: URL -> _Response (or an exception to raise). Records each request."""
    seen = []

    def fake(parts, address, deadline):
        url = f"{parts.scheme}://{parts.hostname}{parts.path or '/'}"
        seen.append((url, address))
        result = routes[url]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(webpage, "_request", fake)
    return seen


def _html(body, status=200):
    return _Response(status, {"content-type": "text/html; charset=utf-8"}, body)


# --- Addresses -------------------------------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("kettle.example/privacy", "https://kettle.example/privacy"),
    ("  https://kettle.example/  ", "https://kettle.example/"),
    ("http://kettle.example", "http://kettle.example"),
])
def test_normalize_url_assumes_https(raw, expected):
    assert webpage.normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "https://a.example/" + "x" * 2100])
def test_normalize_url_rejects_empty_and_huge(raw):
    with pytest.raises(FetchError) as err:
        webpage.normalize_url(raw)
    assert err.value.status_code == 400


@pytest.mark.parametrize("url, message", [
    ("ftp://kettle.example/privacy", "Only http and https"),
    ("file:///etc/passwd", "Only http and https"),
    ("javascript:alert(1)", "Only http and https"),
    ("https://user:pass@kettle.example/", "user name or password"),
    ("https://kettle.example:8443/", "standard ports"),
    ("http://kettle.example:22/", "standard ports"),
    ("http://kettle.example:99999/", "doesn't look like a web address"),
    ("https:///privacy", "doesn't look like a web address"),
])
def test_check_url_refuses_unsafe_addresses(url, message):
    with pytest.raises(FetchError) as err:
        webpage.check_url(url)
    assert message in err.value.message and err.value.status_code == 400


@pytest.mark.parametrize("url", ["https://kettle.example/privacy", "http://kettle.example:80/", "https://kettle.example:443/a?b=1"])
def test_check_url_accepts_standard_addresses(url):
    assert webpage.check_url(url).hostname == "kettle.example"


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
    "198.18.0.1", "224.0.1.1", "255.255.255.255", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1",
    "::ffff:10.0.0.1", "2002:7f00:1::1", "64:ff9b::7f00:1", "::",
])
def test_private_loopback_and_link_local_addresses_are_refused(monkeypatch, address):
    _dns(monkeypatch, {"sneaky.example": [address]})
    with pytest.raises(FetchError) as err:
        webpage.resolve_public("sneaky.example", 443)
    assert "private or local network" in err.value.message and err.value.status_code == 400


def test_a_hostname_with_any_private_answer_is_refused(monkeypatch):
    _dns(monkeypatch, {"mixed.example": ["93.184.216.34", "10.0.0.7"]})
    with pytest.raises(FetchError, match="private or local network"):
        webpage.resolve_public("mixed.example", 443)


def test_public_addresses_are_allowed(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34", "2606:2800:220:1::", "93.184.216.34"]})
    assert webpage.resolve_public("kettle.example", 443) == ["93.184.216.34", "2606:2800:220:1::"]


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://[::1]/", "http://localhost/", "http://169.254.169.254/latest/meta-data/"])
def test_fetch_refuses_local_targets_before_connecting(monkeypatch, url):
    # Real resolution of literals and localhost needs no network.
    monkeypatch.setattr(webpage, "_request", lambda *a: pytest.fail("connected to a private address"))
    with pytest.raises(FetchError, match="private or local network"):
        webpage.fetch(url)


def test_unknown_hosts_get_a_plain_message(monkeypatch):
    _dns(monkeypatch, {})
    with pytest.raises(FetchError, match="couldn't find that website"):
        webpage.resolve_public("nowhere.example", 443)


# --- Requests and redirects ------------------------------------------------------------------


def test_fetch_connects_to_the_checked_address(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"]})
    seen = _serve(monkeypatch, {"https://kettle.example/privacy": _html(POLICY_HTML)})
    page = webpage.fetch("https://kettle.example/privacy")
    assert (page.kind, page.url, page.charset) == ("html", "https://kettle.example/privacy", "utf-8")
    assert seen == [("https://kettle.example/privacy", "93.184.216.34")]


def test_redirects_are_followed_and_each_target_is_checked(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"], "www.kettle.example": ["93.184.216.35"]})
    _serve(monkeypatch, {
        "http://kettle.example/privacy": _Response(301, {"location": "https://www.kettle.example/privacy"}),
        "https://www.kettle.example/privacy": _html(POLICY_HTML),
    })
    assert webpage.fetch("http://kettle.example/privacy").url == "https://www.kettle.example/privacy"


def test_a_redirect_to_a_private_address_is_refused(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"], "internal.example": ["10.1.2.3"]})
    seen = _serve(monkeypatch, {"https://kettle.example/privacy": _Response(302, {"location": "http://internal.example/admin"})})
    with pytest.raises(FetchError, match="private or local network"):
        webpage.fetch("https://kettle.example/privacy")
    assert len(seen) == 1


def test_a_redirect_to_another_scheme_is_refused(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"]})
    _serve(monkeypatch, {"https://kettle.example/p": _Response(302, {"location": "file:///etc/passwd"})})
    with pytest.raises(FetchError, match="Only http and https"):
        webpage.fetch("https://kettle.example/p")


def test_redirect_loops_stop(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"]})
    seen = _serve(monkeypatch, {"https://kettle.example/a": _Response(302, {"location": "/a"})})
    with pytest.raises(FetchError, match="redirected too many times"):
        webpage.fetch("https://kettle.example/a")
    assert len(seen) == webpage.MAX_REDIRECTS + 1


@pytest.mark.parametrize("status, message", [
    (403, "block automated visitors"), (429, "block automated visitors"), (503, "block automated visitors"),
    (404, "no page at that address"), (500, r"returned an error \(500\)"),
])
def test_error_statuses_suggest_what_to_do(monkeypatch, status, message):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"]})
    _serve(monkeypatch, {"https://kettle.example/p": _Response(status, {})})
    with pytest.raises(FetchError, match=message):
        webpage.fetch("https://kettle.example/p")


def test_pdf_and_text_are_recognised_and_other_types_refused(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"]})
    _serve(monkeypatch, {
        "https://kettle.example/p.pdf": _Response(200, {"content-type": "application/pdf"}, b"%PDF-1.4 ..."),
        "https://kettle.example/p.txt": _Response(200, {"content-type": "text/plain"}, b"Privacy"),
        "https://kettle.example/p.png": _Response(200, {"content-type": "image/png"}, b"\x89PNG"),
    })
    assert webpage.fetch("https://kettle.example/p.pdf").kind == "pdf"
    assert webpage.fetch("https://kettle.example/p.txt").kind == "text"
    with pytest.raises(FetchError) as err:
        webpage.fetch("https://kettle.example/p.png")
    assert err.value.status_code == 415


# --- Reading pages ---------------------------------------------------------------------------


def test_read_html_keeps_the_main_text_and_drops_page_chrome():
    doc = webpage.read_html(POLICY_HTML)
    assert doc.title == "Privacy policy | Kettle"
    assert doc.text.startswith("Privacy policy\n\n1. Section\n\nWe collect personal data")
    assert "• Access" in doc.text and "track()" not in doc.text and "Home" not in doc.text
    assert ("/terms", "Terms") in doc.links and doc.scripts == 1


def test_read_html_uses_the_meta_charset():
    body = '<meta charset="iso-8859-1"><p>Café policy</p>'.encode("latin-1")
    assert "Café policy" in webpage.read_html(body).text


def test_find_policy_link_prefers_privacy_over_terms():
    links = webpage.read_html(HOME_HTML).links
    assert webpage.find_policy_link(links, "https://kettle.example/") == "https://kettle.example/legal/privacy-policy"
    assert webpage.find_policy_link([("/terms", "Terms of use")], "https://kettle.example/") == "https://kettle.example/terms"
    assert webpage.find_policy_link([("mailto:privacy@kettle.example", "Privacy")], "https://kettle.example/") is None
    assert webpage.find_policy_link([("javascript:void(0)", "Privacy")], "https://kettle.example/") is None


def test_a_homepage_is_followed_to_its_privacy_policy(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"]})
    _serve(monkeypatch, {
        "https://kettle.example/": _html(HOME_HTML),
        "https://kettle.example/legal/privacy-policy": _html(POLICY_HTML),
    })
    policy = webpage.fetch_policy("kettle.example")
    assert policy.url == "https://kettle.example/legal/privacy-policy"
    assert policy.found_from == "https://kettle.example"
    assert policy.title == "Privacy policy | Kettle" and "grievance officer" in policy.text


def test_a_policy_page_is_read_directly(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"]})
    _serve(monkeypatch, {"https://kettle.example/privacy": _html(POLICY_HTML)})
    policy = webpage.fetch_policy("https://kettle.example/privacy")
    assert policy.found_from is None and policy.kind == "html"


def test_javascript_only_pages_say_to_paste_instead(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"]})
    _serve(monkeypatch, {"https://kettle.example/privacy": _html(
        b"<html><body><div id='root'></div><script src='/app.js'></script><noscript>Enable JavaScript</noscript></body></html>")})
    with pytest.raises(FetchError, match="JavaScript.*paste it instead"):
        webpage.fetch_policy("https://kettle.example/privacy")


def test_bot_check_pages_say_to_paste_instead(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"]})
    _serve(monkeypatch, {"https://kettle.example/privacy": _html(
        b"<html><head><title>Just a moment...</title></head><body><script src='/cdn-cgi/challenge-platform/x'></script></body></html>")})
    with pytest.raises(FetchError, match="bot check"):
        webpage.fetch_policy("https://kettle.example/privacy")


def test_pages_that_are_not_policies_are_refused(monkeypatch):
    _dns(monkeypatch, {"kettle.example": ["93.184.216.34"]})
    _serve(monkeypatch, {"https://kettle.example/": _html(b"<h1>Dinner, sorted</h1><p>Weekly meal kits.</p>")})
    with pytest.raises(FetchError, match="doesn't look like a privacy policy"):
        webpage.fetch_policy("https://kettle.example/")


def test_display_url():
    assert webpage.display_url("https://kettle.example/legal/privacy?x=1") == "kettle.example/legal/privacy"
    assert webpage.display_url("https://kettle.example/") == "kettle.example"


# --- End to end, over a real socket on 127.0.0.1 --------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.seen_agents.append(self.headers.get("User-Agent"))
        if self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", "/privacy")
            self.end_headers()
        elif self.path == "/privacy":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(POLICY_HTML)))
            self.end_headers()
            self.wfile.write(POLICY_HTML)
        elif self.path == "/huge":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()  # no Content-Length: the cap has to stop the read
            try:
                for _ in range(64):
                    self.wfile.write(b"<p>" + b"x" * 65536 + b"</p>")
            except OSError:
                pass
        elif self.path == "/slow":
            time.sleep(1.5)
            self.send_response(200)
            self.end_headers()


@pytest.fixture
def local_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.seen_agents = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # The only two checks relaxed for these tests: a loopback address and a non-standard port.
    monkeypatch.setattr(webpage, "_is_public", lambda ip: True)
    monkeypatch.setattr(webpage, "_port_allowed", lambda scheme, port: True)
    yield f"http://127.0.0.1:{server.server_address[1]}", server
    server.shutdown()
    server.server_close()


def test_real_fetch_follows_a_redirect_and_sends_the_user_agent(local_server):
    base, server = local_server
    policy = webpage.fetch_policy(base + "/moved")
    assert policy.url == base + "/privacy" and "grievance officer" in policy.text
    assert server.seen_agents == [webpage.USER_AGENT, webpage.USER_AGENT]


def test_real_fetch_stops_at_the_size_cap(local_server, monkeypatch):
    monkeypatch.setattr(webpage, "MAX_BYTES", 256 * 1024)
    base, _ = local_server
    with pytest.raises(FetchError) as err:
        webpage.fetch(base + "/huge")
    assert err.value.status_code == 413


def test_real_fetch_times_out(local_server, monkeypatch):
    monkeypatch.setattr(webpage, "TIMEOUT", 0.5)
    base, _ = local_server
    started = time.monotonic()
    with pytest.raises(FetchError) as err:
        webpage.fetch(base + "/slow")
    assert err.value.status_code == 504 and time.monotonic() - started < 1.4
