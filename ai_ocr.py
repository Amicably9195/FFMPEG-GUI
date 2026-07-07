#!/usr/bin/env python3
"""ai_ocr - AI text reading for Drawing2CAD, powered by the Claude API.

Tesseract is good at FINDING text on a drawing but often misreads it
(foot marks become '!', hand lettering becomes gibberish). Claude's vision
actually understands what is written: it reads drafting lettering, fixes
"40.00!" to "40.00'" from context, and returns "" for scribbles.

Flow: every text region Tesseract located is cropped, rotated upright,
stacked onto numbered contact sheets, and sent to Claude in a handful of
requests per drawing (typically a few cents total). Claude's transcriptions
replace Tesseract's guesses.

Needs an Anthropic API key: the ANTHROPIC_API_KEY environment variable,
or a key saved via the GUI (stored in ~/.drawing2cad.json).
"""

import base64
import json
import os
import re

import cv2
import numpy as np

try:
    import anthropic
    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False

DEFAULT_MODEL = "claude-opus-4-8"
CONFIG_PATH = os.path.expanduser("~/.drawing2cad.json")

ROW_H = 48        # crop rows are normalized to this height on the sheet
LABEL_W = 90      # left margin for the row number
SHEET_MAX_W = 900
ROWS_PER_SHEET = 30

PROMPT = (
    "These are numbered text snippets cropped from a scanned technical "
    "drawing (survey / architectural plan). Each row is one label. "
    "Transcribe each row exactly as written. Use ' for the feet mark and "
    '" for the inch mark (e.g. 40.00\', 5\'-6"). Preserve numbers and '
    "punctuation precisely. If a row is unreadable or contains no real "
    "text, use an empty string. Respond with ONLY a JSON object mapping "
    'each row number to its transcription, e.g. {"1": "BRICK GARAGE", '
    '"2": "40.00\'"}.'
)


def saved_key():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f).get("api_key") or None
    except (OSError, ValueError):
        return None


def save_key(key):
    data = {}
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data["api_key"] = key
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f)


def resolve_key(explicit=None):
    return explicit or os.environ.get("ANTHROPIC_API_KEY") or saved_key()


def available(explicit_key=None):
    return _HAS_SDK and bool(resolve_key(explicit_key))


def _crop_upright(gray, wd, pad=4):
    """Cut the word's box out of the image and rotate it to read left-right."""
    x0 = max(0, int(wd["x"]) - pad)
    y0 = max(0, int(wd["y"]) - pad)
    x1 = min(gray.shape[1], int(wd["x"] + wd["w"]) + pad)
    y1 = min(gray.shape[0], int(wd["y"] + wd["h"]) + pad)
    img = gray[y0:y1, x0:x1]
    if img.size == 0:
        return None
    if wd["rotation"] == 90:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif wd["rotation"] == 270:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def _build_sheet(crops):
    """Stack crops into one numbered contact-sheet image; returns (png bytes)."""
    rows = []
    for idx, crop in crops:
        h, w = crop.shape
        scale = ROW_H / float(h)
        new_w = min(SHEET_MAX_W - LABEL_W, max(8, int(w * scale)))
        resized = cv2.resize(crop, (new_w, ROW_H))
        row = np.full((ROW_H + 8, SHEET_MAX_W), 255, dtype=np.uint8)
        cv2.putText(row, f"{idx}:", (4, ROW_H - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, 0, 2)
        row[4:4 + ROW_H, LABEL_W:LABEL_W + new_w] = resized
        cv2.line(row, (0, ROW_H + 6), (SHEET_MAX_W, ROW_H + 6), 200, 1)
        rows.append(row)
    sheet = np.vstack(rows)
    ok, buf = cv2.imencode(".png", sheet)
    return buf.tobytes() if ok else None


def _parse_reply(text):
    """Parse Claude's JSON reply, tolerating code fences and stray prose."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        return {str(k): str(v) for k, v in data.items()}
    except ValueError:
        out = {}
        for k, v in re.findall(r'"(\d+)"\s*:\s*"((?:[^"\\]|\\.)*)"', m.group(0)):
            out[k] = v.replace('\\"', '"').replace("\\\\", "\\")
        return out


def refine_words(gray, words, api_key=None, model=DEFAULT_MODEL, log=print,
                 client=None):
    """Re-read every located text region with Claude vision. Mutates the
    word dicts in place (text, conf); words Claude calls empty get conf 0
    so downstream filtering drops them. Returns how many labels changed."""
    key = resolve_key(api_key)
    if client is None:
        if not _HAS_SDK:
            raise RuntimeError("anthropic package not installed")
        if not key:
            raise RuntimeError("no Anthropic API key configured")
        client = anthropic.Anthropic(api_key=key)

    crops = []
    for i, wd in enumerate(words):
        crop = _crop_upright(gray, wd)
        if crop is not None:
            crops.append((i, crop))

    changed = 0
    for start in range(0, len(crops), ROWS_PER_SHEET):
        batch = crops[start:start + ROWS_PER_SHEET]
        sheet = _build_sheet([(j + 1, c) for j, (_, c) in enumerate(batch)])
        if sheet is None:
            continue
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/png",
                                "data": base64.standard_b64encode(sheet)
                                .decode("ascii")}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
        )
        if response.stop_reason == "refusal":
            log("  AI reading declined a batch - keeping Tesseract text "
                "for it.")
            continue
        reply = next((b.text for b in response.content if b.type == "text"),
                     "")
        results = _parse_reply(reply)
        for j, (word_idx, _) in enumerate(batch):
            new = results.get(str(j + 1))
            if new is None:
                continue
            wd = words[word_idx]
            new = new.strip()
            if not new:
                wd["conf"] = 0.0  # Claude says it isn't text - drop it
                changed += 1
            else:
                if new != wd["text"]:
                    changed += 1
                wd["text"] = new
                wd["conf"] = 95.0
        log(f"  AI read batch {start // ROWS_PER_SHEET + 1}/"
            f"{(len(crops) + ROWS_PER_SHEET - 1) // ROWS_PER_SHEET} "
            f"({len(batch)} labels).")
    return changed
