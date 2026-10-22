import contextlib
import io
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scrapecreators import Client, ScrapeCreatorsError, next_cursor  # noqa: E402
from scrapecreators.cli import load_endpoints, main, render  # noqa: E402

REQUESTS = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        REQUESTS.append((u.path, q, self.headers.get("x-api-key")))
        if u.path == "/boom":
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":"bad"}')
            return
        if q.get("cursor") == "2":
            body = {"items": [{"id": 3}], "cursor": None}
        elif q.get("cursor") == "1":
            body = {"items": [{"id": 2}], "cursor": "2"}
        else:
            body = {"items": [{"id": 1, "user": {"name": "a"}}], "cursor": "1"}
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *a):
        pass


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        REQUESTS.clear()
        self.client = Client("sk_test", base_url=self.url, retries=0)

    def test_sends_api_key_and_params(self):
        self.client.get("/v1/x", {"handle": "a", "skip": None})
        path, q, key = REQUESTS[0]
        self.assertEqual((path, q, key), ("/v1/x", {"handle": "a"}, "sk_test"))

    def test_paginate_follows_cursor(self):
        pages = list(self.client.paginate("/v1/x", {}, 10, {"cursor"}))
        self.assertEqual(len(pages), 3)

    def test_paginate_respects_max_pages(self):
        self.assertEqual(len(list(self.client.paginate("/v1/x", {}, 2))), 2)

    def test_http_error(self):
        with self.assertRaises(ScrapeCreatorsError) as ctx:
            self.client.get("/boom")
        self.assertEqual(ctx.exception.status, 400)

    def test_missing_key(self):
        import os

        old = os.environ.pop("SCRAPECREATORS_API_KEY", None)
        try:
            with self.assertRaises(ScrapeCreatorsError):
                Client()
        finally:
            if old:
                os.environ["SCRAPECREATORS_API_KEY"] = old

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv), client=self.client)
        return code, out.getvalue(), err.getvalue()

    def test_cli_call_with_alias_and_underscore_param(self):
        code, out, _ = self.run_cli("tt", "profile-videos", "--handle", "abc", "--sort-by=popular")
        self.assertEqual(code, 0)
        path, q, _ = REQUESTS[0]
        self.assertEqual(path, "/v3/tiktok/profile/videos")
        self.assertEqual(q, {"handle": "abc", "sort_by": "popular"})
        self.assertIn('"items"', out)

    def test_cli_missing_required(self):
        code, _, err = self.run_cli("tiktok", "profile-videos")
        self.assertEqual(code, 1)
        self.assertIn("--handle", err)

    def test_cli_unknown_param_and_command(self):
        self.assertEqual(self.run_cli("tiktok", "profile", "--nope", "1")[0], 1)
        self.assertEqual(self.run_cli("tiktok", "nothing")[0], 1)
        self.assertEqual(self.run_cli("nowhere", "x")[0], 1)

    def test_cli_csv_all_pages(self):
        # reddit post-comments accepts cursor
        code, out, _ = self.run_cli(
            "reddit", "post-comments", "--url", "u", "--all-pages", "--format", "csv"
        )
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 4)  # header + 3 rows
        self.assertIn("user.name", lines[0])

    def test_batch_input(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# comment\nalice\n\nbob\n")
        code, out, err = self.run_cli("tiktok", "profile", "--input", f.name, "--input-param", "handle")
        self.assertEqual(code, 0)
        self.assertEqual([r[1]["handle"] for r in REQUESTS], ["alice", "bob"])
        self.assertIn("2 request(s)", err)

    def test_batch_defaults_to_first_required_param(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("u1\nu2\n")
        self.assertEqual(self.run_cli("tiktok", "profile-videos", "--input", f.name)[0], 0)
        self.assertEqual([r[1]["handle"] for r in REQUESTS], ["u1", "u2"])

    def test_list_and_describe(self):
        self.assertEqual(self.run_cli("list")[0], 0)
        self.assertIn("profile", self.run_cli("list", "tiktok")[1])
        self.assertIn("--handle", self.run_cli("describe", "tiktok", "profile")[1])


class UnitTests(unittest.TestCase):
    def test_next_cursor(self):
        self.assertEqual(next_cursor({"cursor": "z"}), ("cursor", "z"))
        self.assertEqual(next_cursor({"max_cursor": 5, "has_more": False}), (None, None))
        self.assertEqual(next_cursor({"cursor": "z"}, {"max_cursor"}), (None, None))

    def test_jsonl(self):
        self.assertEqual(render([{"a": [{"x": 1}, {"x": 2}]}], "jsonl").count("\n"), 2)

    def test_registry_covers_main_platforms(self):
        e = load_endpoints()
        for p in ["tiktok", "instagram", "youtube", "facebook", "twitter", "reddit", "linkedin"]:
            self.assertIn(p, e)
        self.assertGreaterEqual(sum(len(v) for v in e.values()), 100)


if __name__ == "__main__":
    unittest.main()
