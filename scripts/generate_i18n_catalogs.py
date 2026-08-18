"""Generate reviewed static locale modules from the application-owned catalog."""
from __future__ import annotations

import json
import os
import pprint
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mindes_ui.i18n.en import STRINGS as EN_STRINGS  # noqa: E402
from mindes_ui.i18n.zh_cn import STRINGS as ZH_CN_STRINGS  # noqa: E402

PLACEHOLDER = re.compile(r"\{[^{}]+\}")
SEPARATOR = "\nZXQMINDESTEXTSEPARATORQXZ\n"
TARGETS = {
    "zh_tw": ("zh-CN", "zh-TW", ZH_CN_STRINGS),
    "de": ("en", "de", EN_STRINGS),
    "fr": ("en", "fr", EN_STRINGS),
    "es": ("en", "es", EN_STRINGS),
    "ru": ("en", "ru", EN_STRINGS),
    "ko": ("en", "ko", EN_STRINGS),
    "ja": ("en", "ja", EN_STRINGS),
}


def protect(text: str) -> tuple[str, list[str]]:
    placeholders: list[str] = []

    def replace(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"ZXQPH{len(placeholders) - 1}QXZ"

    return PLACEHOLDER.sub(replace, text), placeholders


def restore(text: str, placeholders: list[str]) -> str:
    for index, value in enumerate(placeholders):
        for token in (f"ZXQPH{index}QXZ", f"ZXQPH{index} QXZ"):
            text = text.replace(token, value)
    return text


def request_translation(text: str, source: str, target: str) -> str:
    if os.environ.get("MINDES_TRANSLATION_BACKEND") == "bing":
        import translators as translators_client

        return str(
            translators_client.translate_text(
                text,
                translator="bing",
                from_language=source,
                to_language=target,
            )
        )
    data = urllib.parse.urlencode(
        {
            "client": "dict-chrome-ex",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text,
        }
    ).encode()
    request = urllib.request.Request(
        "https://clients5.google.com/translate_a/t", data=data
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            time.sleep(min(60, 5 * (attempt + 1)))
        except urllib.error.URLError:
            if attempt == 3:
                raise
            time.sleep(min(60, 5 * (attempt + 1)))
    return "".join(segment[0] for segment in payload[0] if segment[0])


def translate_catalog(
    source: dict[str, str], source_code: str, target: str, cache_path: Path
) -> dict[str, str]:
    result: dict[str, str] = (
        json.loads(cache_path.read_text(encoding="utf-8"))
        if cache_path.exists()
        else {}
    )
    items = list(source.items())
    start = len(result)
    while start < len(items):
        end = start
        size = 0
        while end < len(items) and end - start < 24:
            candidate_size = len(items[end][1]) + len(SEPARATOR)
            if end > start and size + candidate_size > 850:
                break
            size += candidate_size
            end += 1
        chunk = items[start:end]
        protected = [protect(value) for _, value in chunk]
        translated = request_translation(
            SEPARATOR.join(value for value, _ in protected), source_code, target
        ).split(SEPARATOR)
        if len(translated) != len(chunk):
            translated = [
                request_translation(value, source_code, target)
                for value, _ in protected
            ]
        for (key, _), value, (_, placeholders) in zip(chunk, translated, protected):
            result[key] = restore(value, placeholders)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{target}: {min(start + len(chunk), len(items))}/{len(items)}", flush=True)
        time.sleep(1.5)
        start = end
    return result


def main() -> None:
    output_dir = ROOT / "src" / "mindes_ui" / "i18n"
    selected = set(sys.argv[1:])
    targets = {
        module: config
        for module, config in TARGETS.items()
        if not selected or module in selected
    }
    for module, (source_code, target, source) in targets.items():
        catalog = translate_catalog(
            source, source_code, target, ROOT / "build" / f"i18n-cache-{module}.json"
        )
        body = "from __future__ import annotations\n\nSTRINGS: dict[str, str] = "
        body += pprint.pformat(catalog, sort_dicts=False, width=110)
        body += "\n"
        (output_dir / f"{module}.py").write_text(body, encoding="utf-8")
        print(f"generated {module}: {len(catalog)} entries", flush=True)


if __name__ == "__main__":
    main()
