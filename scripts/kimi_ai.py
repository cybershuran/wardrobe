#!/usr/bin/env python3
"""Bridge between the wardrobe Vite backend and Kimi's image_generation plugin
gateway (agent-gw).

The app used to call an OpenAI-compatible API (chat completions + image edits)
with AI_API_KEY. This bridge replaces both calls with the agent-gw SDK — the
same gateway the `image_generation` Kimi plugin uses:

  detect    Vision pass: identify garments in a photo, prints the model's JSON
            answer ({"items": [...]}) to stdout.
  generate  Text-to-image with optional local reference images. Local files are
            uploaded through agent-gw storage first (the gateway only accepts
            public reference URLs), then `generate_image` runs and the result
            is downloaded to --output.

Credentials resolve exactly like the plugin: KIMI_API_KEY / KIMI_BASE_URL env,
or ~/.kimi/agent-gw.json ({"api_key": ..., "base_url": ...}).

Requires: agent-gw >= 0.2.6 (pip install the wheel, see scripts/setup-kimi.sh).
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import subprocess
import sys
from pathlib import Path

DEFAULT_TIMEOUT = 300.0
CURL_TIMEOUT = 300.0
DEFAULT_VISION_MODEL = "kimi-for-coding"

BACKGROUND_ENUM = {
    "opaque": "IMAGE_BACKGROUND_OPAQUE",
    "transparent": "IMAGE_BACKGROUND_TRANSPARENT",
}

MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
}

VISION_PROMPT = """Identify every distinct wearable clothing item visible in this image. A photo may show one isolated garment or a person wearing several items. Return one record per actual item that should enter a wardrobe. Ignore the person's body and non-wearable background objects.

Respond with a JSON object of the shape {"items": [...]} and nothing else. Each item must have:
- "name": a concise, specific garment name.
- "part": exactly one of "upperbody", "wholebody_up", "lowerbody", "accessories_up", "shoes".
- "color": primary color as a #rrggbb hex string.
- "secondaryColor": a genuinely distinct secondary #rrggbb hex string, or null.
- "tags": 1-4 useful lowercase detail tags.
- "boundingBox": a tight box around only that item, {"x","y","width","height"} as integers normalized to a 1000 by 1000 image. Boxes may overlap when garments overlap, but each box must focus on one distinct item."""


def _client():
    try:
        from agent_gw import AgentGwClient, AgentGwError
    except ModuleNotFoundError:
        print(
            "Missing dependency: agent-gw >= 0.2.6. Install it with:\n"
            "  .venv/bin/pip install https://cdn.kimi.com/agentgw/pysdk/v0.2.6/agent_gw-0.2.6-py3-none-any.whl",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return AgentGwClient, AgentGwError


def _upload_public_url(client, image_path: str) -> str:
    path = Path(image_path)
    content_type = mimetypes.guess_type(path.name)[0] or "image/png"
    obj = client.upload_storage(path, filename=path.name, content_type=content_type)
    signed_url = obj.get("signed_url") if isinstance(obj, dict) else None
    if not signed_url:
        raise RuntimeError(f"upload_storage returned no signed_url for '{image_path}'")
    return signed_url


def _download(url: str, output: Path, mime_type: str | None) -> Path:
    target = output
    if mime_type:
        wanted = MIME_EXT.get(mime_type.lower())
        if wanted and target.suffix.lower() != wanted:
            target = target.with_suffix(wanted)
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["curl", "-fsSL", url, "-o", str(target)], timeout=CURL_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"failed to download generated image from {url}")
    return target


def cmd_detect(args: argparse.Namespace) -> int:
    image = Path(args.image)
    if not image.is_file():
        print(f"detect input not found: {image}", file=sys.stderr)
        return 2
    mime = mimetypes.guess_type(image.name)[0] or "image/jpeg"
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")
    client_cls, error_cls = _client()
    try:
        with client_cls(timeout=DEFAULT_TIMEOUT) as client:
            result = client.chat_completion(
                model=args.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                        ],
                    }
                ],
                timeout=DEFAULT_TIMEOUT,
            )
    except error_cls as exc:
        print(f"Error detecting garments: {exc}", file=sys.stderr)
        return 1
    content = (
        result.get("choices", [{}])[0].get("message", {}).get("content")
        if isinstance(result, dict)
        else None
    )
    if isinstance(content, list):  # some gateways return content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not content or not str(content).strip():
        print("The vision response was empty", file=sys.stderr)
        return 1
    print(str(content).strip())
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    output = Path(args.output)
    client_cls, error_cls = _client()
    try:
        with client_cls(timeout=DEFAULT_TIMEOUT) as client:
            reference_urls = [_upload_public_url(client, ref) for ref in args.reference or []]
            resp = client.tools.generate_image(
                args.prompt,
                ratio=args.ratio,
                resolution=args.resolution,
                background=BACKGROUND_ENUM[args.background],
                reference_image_urls=reference_urls or None,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            media = data.get("media") if isinstance(data, dict) else None
            url = media.get("url") if isinstance(media, dict) else None
            mime_type = media.get("mime_type") if isinstance(media, dict) else None
    except error_cls as exc:
        print(f"Error generating image: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # upload / network failures
        print(f"Error generating image: {exc}", file=sys.stderr)
        return 1
    if not url:
        print("generate_image returned no media URL", file=sys.stderr)
        return 1
    saved = _download(url, output, mime_type)
    print(json.dumps({"saved": str(saved)}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    detect = sub.add_parser("detect", help="Detect garments in a photo; prints JSON")
    detect.add_argument("--image", required=True, help="Local image path (jpg/png)")
    detect.add_argument("--model", default=DEFAULT_VISION_MODEL, help="Vision model name")
    detect.set_defaults(func=cmd_detect)

    gen = sub.add_parser("generate", help="Generate an image, optionally from local references")
    gen.add_argument("--prompt", required=True, help="Text description / instructions")
    gen.add_argument("--output", required=True, help="Local output path (.png/.jpg)")
    gen.add_argument("--ratio", default="1:1", choices=["1:1", "3:2", "2:3", "16:9", "9:16"])
    gen.add_argument("--resolution", default="1K", choices=["1K", "2K", "4K"])
    gen.add_argument("--background", default="opaque", choices=list(BACKGROUND_ENUM))
    gen.add_argument("--reference", action="append", metavar="LOCAL_IMAGE",
                     help="Local reference image path; repeat for multiple. Uploaded via agent-gw storage first.")
    gen.set_defaults(func=cmd_generate)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
