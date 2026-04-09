"""
Threads Profile Scraper — Playwright + GraphQL interception

Scrapes recent posts from a Threads user profile page.
No API key required. Uses headless Chromium to intercept
the GraphQL responses that Threads loads in the background.

Usage:
    python3 scrape_threads.py <username> [max_scroll]

Output:
    JSON array to stdout, sorted by time (newest first).
"""
import json
import asyncio
import sys
from typing import Dict, List
from playwright.async_api import async_playwright
from nested_lookup import nested_lookup


def parse_post(post_data: Dict) -> Dict | None:
    """Extract structured post data from a raw GraphQL post object."""
    if not isinstance(post_data, dict):
        return None
    try:
        caption = post_data.get("caption") or {}
        text = caption.get("text", "")
        user = post_data.get("user") or {}
        author = user.get("username", "")
        if not author:
            return None

        return {
            "id": post_data.get("id", post_data.get("pk", "")),
            "code": post_data.get("code", ""),
            "text": text,
            "author": author,
            "likes": post_data.get("like_count", 0),
            "reply_count": (post_data.get("text_post_app_info") or {}).get(
                "direct_reply_count", 0
            ),
            "taken_at": post_data.get("taken_at", 0),
        }
    except Exception:
        return None


async def scrape_profile(username: str, max_scroll: int = 5) -> List[Dict]:
    """Scrape a Threads profile page for recent posts."""
    posts: Dict[str, Dict] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="zh-TW")
        page = await context.new_page()

        async def handle_response(response):
            if "graphql" not in response.url and "barcelona" not in response.url:
                return
            try:
                data = await response.json()
                for key in ("post", "thread_items"):
                    found = nested_lookup(key, data)
                    for item in found:
                        if isinstance(item, dict):
                            parsed = parse_post(item)
                            if parsed:
                                posts[parsed["id"]] = parsed
                        elif isinstance(item, list):
                            for sub in item:
                                if isinstance(sub, dict):
                                    post_obj = sub.get("post", sub)
                                    parsed = parse_post(post_obj)
                                    if parsed:
                                        posts[parsed["id"]] = parsed
            except Exception:
                pass

        page.on("response", handle_response)

        url = f"https://www.threads.com/@{username}"
        print(f"[scraper] navigating to {url}", file=sys.stderr)
        await page.goto(url, wait_until="networkidle", timeout=30000)

        for i in range(max_scroll):
            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(1500)
            print(
                f"[scraper] scroll {i + 1}/{max_scroll}, posts: {len(posts)}",
                file=sys.stderr,
            )

        # Also try extracting from embedded script data
        html = await page.content()
        from parsel import Selector

        selector = Selector(text=html)
        for script in selector.xpath("//script/text()").getall():
            try:
                start = script.find("{")
                end = script.rfind("}") + 1
                if start == -1 or end == 0:
                    continue
                data = json.loads(script[start:end])
                for item in nested_lookup("post", data):
                    if isinstance(item, dict):
                        parsed = parse_post(item)
                        if parsed:
                            posts[parsed["id"]] = parsed
            except Exception:
                continue

        await browser.close()

    result = list(posts.values())
    result.sort(key=lambda p: p.get("taken_at", 0), reverse=True)
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scrape_threads.py <username> [max_scroll]", file=sys.stderr)
        sys.exit(1)

    username = sys.argv[1]
    max_scroll = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    results = asyncio.run(scrape_profile(username, max_scroll))
    own_posts = [p for p in results if p["author"] == username]

    if own_posts:
        print(json.dumps(own_posts, indent=2, ensure_ascii=False))
        print(f"[scraper] total posts by @{username}: {len(own_posts)}", file=sys.stderr)
    else:
        print("[]")
        print("[scraper] no posts found", file=sys.stderr)


if __name__ == "__main__":
    main()
