# Drawing2CAD — turn photos/scans of drawings into CAD files

Takes a **photo or scan** of a technical drawing (survey, floor plan, DOB
print, etc.) and converts it into a **DXF** file with real CAD geometry:

- **LINES** layer — straight linework (walls, borders, dimension lines)
- **CURVES** layer — traced curves, symbols, thick strokes
- **TEXT** layer — OCRed text placed where it appears on the drawing,
  including vertical/rotated labels

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

1. **Add images** (or drag & drop) — JPG/PNG/TIFF scans or phone photos.
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
| Units per pixel | Scale factor for the output coordinates |
| Min line / specks | Noise filtering — raise these for dirty scans |

## Command line

```
python scan2cad.py drawing.jpg -o drawing.dxf
python scan2cad.py --help          # all options
```

## Install

```
pip install customtkinter tkinterdnd2 opencv-python-headless numpy ezdxf pytesseract pillow
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
