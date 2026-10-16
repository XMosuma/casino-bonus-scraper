
#!/usr/bin/env python3
"""Casino bonus scraper.

Fetches URLs from sources.json, checks robots.txt, uses an LLM
to extract structured bonus fields, and writes bonuses.json.

Backend:
  ANTHROPIC_API_KEY set -> Anthropic API
  Otherwise              -> Local Ollama

Usage: python scraper.py
"""

import datetime
import json
import os
import re
import sys
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

UA = "bonus-screening-task/1.0"
MODEL = os.environ.get("MODEL", "claude-haiku-4-5-20251001")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_URL = os.environ.get(
    "OLLAMA_URL",
    "http://localhost:11434"
).rstrip("/")
# OLLAMA_URL = os.environ.get(
#     "OLLAMA_URL", "http://localhost:11434"
# ).rstrip("/")

MAX_CHARS = 20000

PROMPT = """Extract welcome bonus details from this casino page.

Page URL: {url}
Page title: {title}

Return ONLY a JSON object with exactly these keys:
casino: string
welcome_bonus: string or null
wagering_multiplier: number or null
min_deposit: string with currency or null

Use null when a value is not explicitly stated.
Do not guess, calculate, or invent values.
Use the main welcome offer, not unrelated promotions.
The casino must be the operator the page is about.

Page text:
{text}
"""

KEYWORDS = re.compile(
    r"bonus|wager|rollover|play-?through|deposit|"
    r"free\s+(?:bet|spin)|match|welcome|\b\d+\s?x\b",
    re.I,
)


def allowed(url):
    """Check robots.txt before fetching a page."""
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False

    robots_url = (
        f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    )

    try:
        response = requests.get(
            robots_url,
            headers={"User-Agent": UA},
            timeout=15,
        )
    except requests.RequestException:
        return False

    if response.status_code == 404:
        return True

    if response.status_code != 200:
        return False

    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())

    return parser.can_fetch(UA, url)


def page_text(url):
    """Fetch a page and extract relevant visible text."""
    response = requests.get(
        url,
        headers={"User-Agent": UA},
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    title = (
        soup.title.get_text(strip=True)
        if soup.title
        else ""
    )

    for tag in soup(
        ["script", "style", "noscript", "svg", "nav", "footer"]
    ):
        tag.decompose()

    text = " ".join(soup.get_text(" ").split())

    relevant = [
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if KEYWORDS.search(sentence)
    ]

    return title, " ".join(relevant)[:MAX_CHARS]


def ask_llm(prompt):
    """Use Anthropic when configured, otherwise use Ollama."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        client = anthropic.Anthropic()

        response = client.messages.create(
            model=MODEL,
            max_tokens=400,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        return response.content[0].text

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "options": {
                "num_ctx": 8192,
                "temperature": 0,
            },
            "messages": [
                {"role": "user", "content": prompt}
            ],
        },
        timeout=300,
    )

    response.raise_for_status()
    return response.json()["message"]["content"]


def extract(url, title, text):
    """Ask the LLM to extract the required fields."""
    prompt = PROMPT.format(
        url=url,
        title=title,
        text=text,
    )

    raw = ask_llm(prompt).strip()

    # Support models that wrap JSON in Markdown fences.
    raw = re.sub(
    r"\A```(?:json)?\s*|\s*```\Z",
    "",
    ask_llm(prompt).strip(),
    flags=re.I,
).strip()
    # raw = re.sub(
    #     r"\A```(?:json)?\s*|\s*```\Z",
    #     "",
    #     raw,
    #     flags=re.I,
    # ).strip()

    data = json.loads(raw)

    wagering = data.get("wagering_multiplier")

    if isinstance(wagering, str):
        match = re.search(r"\d+(?:\.\d+)?", wagering)
        # match = re.search(
        #     r"\d+(?:\.\d+)?",
        #     wagering,
        # )
        wagering = float(match.group()) if match else None

    if isinstance(wagering, float) and wagering.is_integer():
        wagering = int(wagering)

    if wagering is not None and (
        isinstance(wagering, bool)
        or not isinstance(wagering, (int, float))
        or wagering < 0
    ):
        wagering = None

    casino = data.get("casino")
    welcome_bonus = data.get("welcome_bonus")
    min_deposit = data.get("min_deposit")

    return {
        "casino": casino if isinstance(casino, str) else None,
        "welcome_bonus": (
            welcome_bonus
            if isinstance(welcome_bonus, str)
            else None
        ),
        "wagering_multiplier": wagering,
        "min_deposit": (
            min_deposit
            if isinstance(min_deposit, str)
            else None
        ),
    }


def num_in_text(number, text):
    """Check whether a number appears in the source text."""
    return re.search(
    rf"(?<![\d,.]){re.escape(number)}(?![\d]|[.,]\d)",
    text,
) is not None
    # return re.search(
    #     rf"(?<![\d,.]){re.escape(number)}(?![\d]|[.,]\d)",
    #     text,
    # ) is not None


def check(fields, text):
    """Reject extracted values containing unsupported numbers."""
    for key in ("welcome_bonus", "min_deposit"):
        value = fields.get(key)

        if not value:
            continue
        numbers = re.findall(r"\d+(?:[,.]\d+)*", value)
        # numbers = re.findall(
        #     r"\d+(?:[,.]\d+)*",
        #     value,
        # )

        if not all(num_in_text(n, text) for n in numbers):
            print(
                f"UNSUPPORTED {key} {value!r}: "
                "numbers not found in source text; setting null",
                file=sys.stderr,
            )
            fields[key] = None

    wagering = fields.get("wagering_multiplier")

    if wagering is not None:
        number = re.escape(str(wagering))

        supported = re.search(
            rf"(?<![\d.,]){number}\s*(?:x|times)\b"
            rf"|\bx\s*{number}(?![\d.,])",
            text,
            re.I,
        )
        # supported = re.search(
        #     rf"(?<![\d.,]){number}\s*(?:x|times)\b"
        #     rf"|\bx\s*{number}(?![\d.,])",
        #     text,
        #     re.I,
        # )

        if not supported:
            print(
                f"UNSUPPORTED wagering_multiplier {wagering!r}: "
                "not found in source text; setting null",
                file=sys.stderr,
            )
            fields["wagering_multiplier"] = None

    return fields


def validate_record(record):
    required = {
        "casino",
        "welcome_bonus",
        "wagering_multiplier",
        "min_deposit",
        "source_url",
    }

    missing = required - record.keys()

    if missing:
        raise ValueError(
            f"Missing required fields: {sorted(missing)}"
        )

    if not isinstance(record["source_url"], str):
        raise ValueError("source_url must be a string")

    if not record["source_url"].startswith(("http://", "https://")):
        raise ValueError("source_url must be an HTTP(S) URL")
    # if not record["source_url"].startswith(("http://", "https://")):
    #     raise ValueError("source_url must be an HTTP(S) URL")

    return True

def main():
    with open("sources.json", encoding="utf-8") as file:
        urls = json.load(file)

    if not isinstance(urls, list) or len(urls) != 3:
        sys.exit("sources.json must contain exactly 3 URLs.")

    if not all(
        isinstance(url, str)
        and urlparse(url).scheme in ("http", "https")
        and urlparse(url).netloc
        for url in urls
    ):
        sys.exit("Every source must be a valid HTTP(S) URL.")

    if any("REPLACE" in url.upper() for url in urls):
        sys.exit("Replace the placeholder URLs in sources.json.")

    if len(set(urls)) != 3:
        sys.exit("Please provide 3 distinct source URLs.")

    backend = (
        f"Anthropic ({MODEL})"
        if os.environ.get("ANTHROPIC_API_KEY")
        else f"Ollama ({OLLAMA_MODEL})"
    )

    print(f"Model backend: {backend}")

    casinos = []
    failed = 0

    for url in urls:
        try:
            print(f"Checking {url}")

            if not allowed(url):
                raise RuntimeError(
                    "robots.txt disallows the URL, or could not "
                    "be checked safely."
                )

            title, text = page_text(url)

            if not text.strip():
                raise RuntimeError("No relevant page text found.")

            fields = extract(url, title, text)
            fields = check(fields, text)

            fields["source_url"] = url
            validate_record(fields)
            casinos.append(fields)

            print(f"OK       {url}")

        except Exception as error:
            failed += 1
            print(
                f"SKIPPED  {url}: {error}",
                file=sys.stderr,
            )

        time.sleep(2)

    output = {
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "model": backend,
        "casinos": casinos,
    }

    with open(
        "bonuses.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"Wrote bonuses.json with {len(casinos)} "
        f"successful casino records."
    )

    if failed:
        print(f"Failed sources: {failed}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
