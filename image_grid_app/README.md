# Image Grid App

Base structure for a FastAPI project that scans folders, batches images, composes image grids, and exports results.

## Structure

- `app/main.py`: FastAPI app setup
- `app/routes/`: UI and API routes
- `app/services/`: domain service modules
- `app/models/`: shared schemas
- `app/templates/`: Jinja templates
- `app/static/`: CSS and JavaScript assets

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

For development, `pip install -r requirements-dev.txt`, then `ruff check .` and
`pytest`.

## UI generation modes

The home page now has a mode selector next to the generation controls. The selector drives a single client-side source of truth for generation requests:

- **Single folder**
  - Labels: `Input folder` + `Output folder`
  - Endpoint: `POST /api/jobs/generate`
- **Batch folders**
  - Labels: `Parent folder` + `Created output folder`
  - Validation endpoint: `POST /api/jobs/scan-selected-batch-folders`
  - Generation endpoint: `POST /api/jobs/generate-all-folders`

`Cover collage` remains a separate single-folder action and still calls `POST /api/jobs/generate-cover-collage`. It is not part of the mode toggle.

## Output quality

Every page-producing endpoint accepts the same print and cleanup options:

| Field | Default | Does |
| --- | --- | --- |
| `page_unit` | `px` | Read `page_width`/`page_height` as `px`, `in` or `mm` |
| `dpi` | `300` | Converts physical units, and is stamped into the exported file |
| `background_clean_mode` | `off` | `flatten` or `transparent` to clean a near-white background |
| `background_tolerance` | `240` | Lowest channel value counted as background |
| `background_feather` | `1` | Mask softening, in pixels, to kill halos |
| `include_partial_page` | `false` | Grid endpoints only: render a partly-filled final page |

Background cleaning flood-fills inward from the image border, so only a
background *connected to the edge* is touched — a white highlight enclosed by
the subject is never reached. An image whose border is not near-white is
reported as having no background and returned unchanged.

## Image loading and background cleaning

Both live in **[mullion](https://github.com/sigrix-io/mullion)**, a small
library this app depends on rather than a module it owns. It is installed from
PyPI, pinned to its minor version (`mullion~=0.2.1`).

`mullion.open_path()` is the one place a source image is opened. It composites
transparency onto white — a bare `convert("RGB")` drops the alpha and leaves the
black underneath showing — and applies EXIF orientation, so a phone photo is not
placed sideways. `mullion.clean_background()` is the cleaner described above,
and `mullion.resolve_page_geometry()` is what turns `page_unit` and `dpi` into
the pixel dimensions the exporter stamps. The grid composer and the cover
collage both go through all three.

It was extracted because the same three problems arrive in every application
that accepts user images, and an app that solves them in six places gets six
different answers. Nothing about the behaviour here changed in the move.
mullion's own suite tests these functions directly; this app's tests check the
same claims through its composer and exporter, so a bad mullion upgrade still
fails here.

## Export behavior

- Exports carry DPI metadata, so the page reports a real physical size instead of
  falling back to 72 DPI.
- Output directories are created automatically when they do not exist.
- Pages are saved with sequential names: `page_001.png`, `page_002.png`, etc. (or `.jpg` for JPG export).
- Export is conflict-safe: existing `page_###` files are **not** overwritten; new exports continue at the next available index.
- Export responses can return saved paths as relative paths (default) or absolute paths.
