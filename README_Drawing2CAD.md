# Drawing2CAD — turn photos/scans of drawings into CAD files

Takes a **photo or scan** of a technical drawing (survey, floor plan, DOB
print, etc.) and converts it into a **DXF** file with real CAD geometry:

- **LINES** layer — straight linework (walls, borders, dimension lines)
- **CURVES** layer — traced curves, symbols, thick strokes
- **TEXT** layer — OCRed text placed where it appears on the drawing,
  including vertical/rotated labels
- **TEXT_REVIEW** layer (red, **hidden by default**) — text the OCR was *not*
  sure about, boxed on the drawing. The file opens clean; turn this layer on
  in CAD when you want to proofread the uncertain spots

It also understands dimensions: labels like `40.00'`, `5'-6"`, `±15'` are
parsed into feet and cross-checked against the drawn line they measure. When
at least three independent dimensions agree, the scale is locked and **the
DXF comes out in real feet** — measure the 40.00' lot line in CAD and it
reads 40.00. Dimensions that contradict the consensus scale (usually an OCR
misread) are flagged red for review.

**Smart text reading (free, offline):** every label Tesseract locates gets
a second opinion from RapidOCR, an open-source neural text reader bundled
with the app — no account, no API, no internet, no cost. The smarter read
only wins when it is clearly more confident than Tesseract's, so it can
rescue hard labels but never degrade good ones.

Dirty scans (old photocopies, blueprints, faxes) are detected automatically
by their speckle grain and get a deep-clean pass: median filtering, a more
sensitive threshold for faint lines, and higher noise floors.

## CAD files in, DWG out (translation tier)

**CAD project files are already vector data**, so converting them is exact
translation, not tracing:

- **DXF in / DXF out** works out of the box (built in).
- **DWG or DGN input**, and **DWG/DGN output**, need a free local converter —
  the **ODA File Converter**
  (https://www.opendesign.com/guestfiles/oda_file_converter). Install it once
  (like Tesseract); the app finds it automatically, or set the
  `ODA_CONVERTER` environment variable to its path. LibreDWG's
  `dwg2dxf`/`dxf2dwg` are also detected as a fallback for DWG.
- Without a converter, DWG/DGN output **falls back to DXF** (which both
  AutoCAD and MicroStation open natively) with a clear message — nothing
  breaks.

In the GUI, pick the **Output** format (DXF / DWG / DGN). On the command line,
just give the output an extension: `scan2cad.py drawing.jpg -o drawing.dwg`.

DXF opens directly in **AutoCAD** and **MicroStation** (in MicroStation just
open the .dxf and *Save As* .dgn if you want a native file). Everything is on
separate layers, so you can change line weights, recolor, or delete the whole
text layer in one click.

> Why DXF and not DWG? DWG is Autodesk's closed format. DXF is the exchange
> format both AutoCAD and MicroStation read and write natively — same
> geometry, no license issues.

## Using the GUI

```
python drawing2cad_gui.py
```

1. **Add files** (or drag & drop) — JPG/PNG/TIFF scans, phone photos, or **PDFs**.
   Vector PDFs (CAD e-filings) are lifted exactly — perfect lines and text, no
   OCR. Scanned PDFs go through the photo pipeline at native scan resolution.
   Multi-page PDFs produce one DXF per page.
2. Leave the default options on and hit **Convert to DXF**.
3. The .dxf is saved next to each image.

Options:

| Option | What it does |
|---|---|
| Auto-crop page | Finds the sheet of paper in a photo and straightens the perspective |
| Straighten (deskew) | Rotates the drawing so lines are square to the axes |
| OCR text | Reads the text (needs Tesseract, see below) |
| Trace curves | Vectorizes curved/round features, not just straight lines |
| Snap lines to axis | Makes almost-horizontal/vertical lines exactly horizontal/vertical |
| Auto-scale to feet | Verifies dimensions against drawn lines and outputs the DXF in feet |
| Flag uncertain text | Puts low-confidence OCR on the red TEXT_REVIEW layer, boxed |
| Deep-clean dirty scans | Auto-detects speckled photocopies and scrubs them before vectorizing |
| Units per pixel | Scale factor for the output coordinates |
| Min line / specks | Noise filtering — raise these for dirty scans |

## Command line

```
python scan2cad.py drawing.jpg -o drawing.dxf
python scan2cad.py --help          # all options
```

## Install

```
pip install customtkinter tkinterdnd2 numpy ezdxf pytesseract pillow pymupdf rapidocr_onnxruntime
pip uninstall -y opencv-python opencv-python-headless
pip install --force-reinstall --no-deps opencv-contrib-python-headless
```

(The last two lines matter: RapidOCR pulls in plain OpenCV, which must be
replaced by the contrib build or line tracing quality drops.)

```
```

For OCR you also need the **Tesseract** engine itself:

- **Windows:** installer from https://github.com/UB-Mannheim/tesseract/wiki
  (the app finds it automatically in the default install folder, or set the
  `TESSERACT_CMD` environment variable to tesseract.exe)
- **Linux:** `sudo apt install tesseract-ocr`
- **macOS:** `brew install tesseract`

Without Tesseract everything still works — you just get linework, no text.

## Building a Windows .exe

```
pyinstaller Drawing2CAD.spec
```

## Tips for good results

- **Shoot straight-on** with the whole sheet in frame and even lighting —
  the flatter the photo, the cleaner the CAD file. A real scan beats a photo.
- Higher resolution = better OCR. 300 DPI scans are ideal.
- The converter puts out geometry in **pixel units** by default. After opening
  in CAD, scale the drawing once against a known dimension (surveys always
  have one, e.g. a 40.00' lot width) and everything is to scale.
- Text at odd angles (not horizontal/vertical) may be missed by OCR — the
  linework underneath is still captured.
- Hand-drawn or very rough plans vectorize, but expect to clean up in CAD.
  This tool does the tedious 90%; it is not a replacement for drafting.
