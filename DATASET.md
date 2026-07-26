# Building the dataset — curated public-domain drawings

The benchmark and (eventual) reader fine-tune are fed from **legally clean**
sources only: curated public-domain / openly-licensed drawings + synthetic
generation. **We never scrape the open web** (DECISIONS.md #7). This is how to
pull the curated real drawings.

> **Legality in one line:** works of the US federal government are public
> domain. The Library of Congress HABS/HAER/HALS collections and USGS maps are
> federal works — free to download and use. State/local and university sources
> vary; check each before use. The downloaders record the license per file.

## Two ways to download — pick one

Both pull from the **same** Library of Congress JSON API, politely (descriptive
User-Agent, a pause between requests, a hard cap) and write each image plus a
`.json` provenance record (source, license, LoC URL) into
`~/.drawing2cad_dataset/architectural/`.

### A. Python (any OS)
```
python dataset_builder.py fetch --source loc_habs_haer
```
Or call it directly for control:
```python
import dataset_builder as d
d.fetch_loc(d.ROOT, category="surveys", count=40)
```

### B. PowerShell (Windows)
```powershell
scripts\fetch_loc_drawings.ps1 -Count 40
```

> **Collection slug:** the default is the combined
> `historic-american-buildings-landscapes-and-engineering-records` (HABS +
> HAER + HALS), confirmed working against the live LoC JSON API. The older
> per-survey slugs (e.g. `historic-american-buildings-survey`) now return 404.

## After downloading
```
python dataset_builder.py degrade <image>   # make hard variants (optional)
python dataset_builder.py split             # assign train/validation/benchmark
python dataset_builder.py stats             # corpus health
```

## Approved sources (see `python dataset_builder.py sources`)

| Source | Content | License |
|---|---|---|
| **Library of Congress HABS/HAER/HALS** *(wired)* | measured architectural / engineering drawings | US Gov — public domain |
| USGS historical topo maps | surveyed maps, legends, scales | US Gov — public domain |
| GSA / NPS / USACE (GPO) | federal building & site plans, manuals | US Gov — public domain |
| ezdxf / ODA samples | reference DXF/DWG fixtures | MIT / vendor sample terms |
| University open courseware | drafting teaching plates | per-institution — verify |

Only `loc_habs_haer` has an automatic downloader today; the rest are
documented. **Adding a downloader for another source** is a deliberate step:
confirm its terms and a stable API, record the decision in DECISIONS.md, then
add a `fetch` callable to its entry in `dataset_builder.APPROVED_SOURCES` — so
every downloader lands inside the approved registry, never as an ad-hoc scrape.

## Notes & etiquette

- Keep `count` modest and `delay >= 2s`. The LoC (and any public API) can and
  will rate-limit heavy automated access; a personal research pull should be
  gentle.
- Some LoC search results are medium-resolution derivatives. For the geometry
  benchmark that is usually fine; for a fine-tune you may want the full-res
  item images (follow each item's `id` URL with `?fo=json` and take
  `resources[0].image`).
- **Not runnable in the dev sandbox** (no outbound network). Run these on a
  connected machine. The JSON field names (`results`, `image_url`) match the
  documented LoC API; if a field has moved, adjust the two lines marked
  `<-- confirm shape` in `dataset_builder.fetch_loc`.
