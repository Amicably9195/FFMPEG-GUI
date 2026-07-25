# Text-tier fine-tune — runbook

Reading is the biggest lever on quality (see STATUS.md and the stress tier:
`python benchmark.py --hard appearance_hard` shows OCR is where degraded scans
fall apart). Everything else runs locally and free; this is the one step that
wants a **one-time GPU**. This runbook makes it turnkey when a GPU is available
— it is deliberately a document, not an unrunnable script, because a training
job that cannot be validated here would violate the project's "ship only what
you measured" rule.

The corpus tooling is already built; this is the recipe to consume it.

---

## What the reader is today

`smart_ocr.py` runs **RapidOCR** (`rapidocr_onnxruntime`), which serves the
open-source **PP-OCR** recognition model as ONNX. It reads machine text well
and drafting/hand lettering poorly. The goal of the fine-tune is a drop-in
replacement recognition model — same input/output contract — that is stronger
on drafting lettering, exported back to ONNX so `smart_ocr` loads it unchanged.

Because RapidOCR's served model is a PP-OCR rec model, the natural, free path
is to **fine-tune PP-OCRv4 rec in PaddleOCR, then export to ONNX**. (TrOCR is a
viable alternative but heavier at inference; keep the PP-OCR path unless there
is a reason to switch — it preserves the current runtime footprint.)

---

## Step 1 — Assemble the corpus (no GPU)

Two label streams, both already in the **same format** on purpose — a
`labels.tsv` of `<image_filename>\t<text>\t<timestamp>` beside the crop PNGs:

- **Synthetic** (unlimited, generate now):
  ```
  python synth_text.py gen -n 50000 --out ~/.drawing2cad_dataset/synth_text
  ```
  Dimensions, room names, notes, callouts in drafting fonts, put through the
  `dataset_builder` degradation recipes. This is the pre-training bulk.

- **Real user corrections** (high value, accumulated from use): the review
  screen writes confirmed `(crop → text)` pairs to
  `~/.drawing2cad_dataset/labels.tsv` via `corrections.save_pair`. A few
  hundred real drafting-lettering pairs are worth far more than synthetic
  bulk — weight them heavily (oversample, or fine-tune on synthetic first then
  on real).

Hold out a validation split (e.g. 5%) — do NOT let a crop leak between train
and val (dedup by content hash, the same discipline `dataset_builder.split`
uses).

## Step 2 — Convert to PaddleOCR rec format (no GPU)

PaddleOCR rec training wants a label file of `image_path\ttext` and a char
dictionary. From our `labels.tsv`:

- Emit `rec_gt_train.txt` / `rec_gt_val.txt` as `relative/crop.png\ttext`
  (drop the timestamp column).
- Build `d2cad_dict.txt` — the sorted unique character set across all labels
  (digits, `A–Z`, `'`, `"`, `-`, `.`, `/`, space, `°` if surveys use
  bearings). Keep it minimal; a smaller alphabet trains faster and misreads
  less.

## Step 3 — Fine-tune (GPU, one-time)

Start from the pretrained `en_PP-OCRv4_rec` weights (or the multilingual rec if
bearings/symbols matter) and fine-tune — do not train from scratch:

- Config: PP-OCRv4 rec, `character_dict_path: d2cad_dict.txt`,
  `use_space_char: true`, your train/val label files.
- Low LR (fine-tune, e.g. 1e-4 with cosine decay), a few epochs; watch val
  accuracy — stop when it plateaus (avoid overfitting the synthetic look).
- Cost: a used 12 GB GPU (RTX 3060 class) or a few dollars of rented GPU; hours
  on a gaming PC. This is the one-time cost the whole project is organized
  around; there is no free frontier-quality shortcut.

## Step 4 — Export to ONNX and drop in

- Export the trained rec model to inference format, then to ONNX
  (`paddle2onnx`).
- Point RapidOCR at the new `rec` ONNX (its `RapidOCR(rec_model_path=...)`),
  or replace the bundled rec model. `smart_ocr.py` needs **no code change** —
  same interface.

## Step 5 — Measure before shipping (the gate)

The fine-tune is only real if it moves the numbers, and it must not regress
clean text:

```
python synth_text.py measure -n 400 --engine rapid   # synthetic drafting text
python benchmark.py                                   # clean guardrail: OCR must NOT drop
python benchmark.py --hard appearance_hard            # the target: stress OCR should rise
```

Record before/after in WORKLOG.md and CHANGELOG.md. Ship the new model only if
stress OCR rises and the clean guardrail holds (AI_RULES #2, #4). If real
correction pairs were used, note how many — the correction flywheel's whole
point is that this number grows and each fine-tune gets better.

---

## Guardrails specific to this step

- **Never let the model hallucinate to look better.** A recognizer that
  confidently invents plausible dimensions is worse than one that returns low
  confidence and lets the review screen catch it (Decision 001). Keep
  `smart_ocr`'s confidence gating (`MIN_SCORE`, `WIN_MARGIN`) — a fine-tuned
  model still only wins when it clearly beats Tesseract.
- **Keep it local and free at inference.** ONNX on CPU, no API. The GPU is
  train-time only.
- **Version the model** alongside `BENCHMARK_VERSION` so a score change is
  attributable to a specific model, not an unknown one.
