# mar_place

## MVP Overview
`mar_place` contains **Image Grid App**, a FastAPI + vanilla JS tool that:
- scans an input folder for supported images,
- estimates page count,
- composes a fixed **4x3 image grid** (12 images) per page,
- exports generated pages as PNG or JPG at a chosen DPI,
- optionally cleans a near-white background off each image before placing it,
- lets the UI toggle between single-folder and batch-folder generation modes.

Project root:
- `image_grid_app/` — runnable application.

---

## Installation and Run Commands

Requires Python 3.11 or newer. The optional preview video also needs
[ffmpeg](https://ffmpeg.org/) on `PATH`.

### 1) Install dependencies
```bash
cd image_grid_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run the app
```bash
cd image_grid_app
uvicorn app.main:app --reload
```

### 3) Open in browser
- UI: `http://127.0.0.1:8000/`
- API docs (Swagger): `http://127.0.0.1:8000/docs`

The app reads and writes files at the paths you give it and has no login, so
keep it on `127.0.0.1` (the default). See [SECURITY.md](SECURITY.md).

### Optional environment variables
- `IMAGE_GRID_INPUT_FOLDER`: prefills the input-folder field, e.g.
  `IMAGE_GRID_INPUT_FOLDER=~/Pictures/clip-art uvicorn app.main:app`.
- `IMAGE_GRID_ALLOWED_HOSTS`: comma-separated host names to accept besides
  `localhost`, `127.0.0.1` and `[::1]`. Only for serving the app under another
  name on purpose.

### Development
```bash
cd image_grid_app
pip install -r requirements-dev.txt
ruff check .
pytest
```
CI runs the same on Python 3.11 and 3.13, with ffmpeg installed so the
preview-video tests encode real files.

---

## Expected Supported File Types
Input scan supports the following image extensions (case-insensitive):
- `.jpg`
- `.jpeg`
- `.png`
- `.webp`

Notes:
- Folder scan is **non-recursive** (only files directly inside the selected folder).
- Export output format supports `PNG` and `JPG`.

---

## Default Setting Values
Default UI values:
- input folder: empty (set `IMAGE_GRID_INPUT_FOLDER` to prefill it)
- `page_width`: `3000`
- `page_height`: `3000`
- `gap`: `30`
- `margin`: `60`
- `format`: `JPG`
- `page_unit`: `px` (also accepts `in` and `mm`, converted at `dpi`)
- `dpi`: `300`
- `background_clean_mode`: `off` (`flatten` or `transparent` to enable)
- `background_tolerance`: `240`
- `background_feather`: `1`
- `include_partial_page`: `false`

Behavior defaults:
- Scan sample size: first `5` files (`sample_files`) in sorted order.
- Images per page: `12` (fixed 4x3).
- Export naming: `page_001`, `page_002`, ...
- Export conflict handling: never overwrite existing `page_###`; continue at next index.

---

## Endpoint Descriptions
Base URL: `http://127.0.0.1:8000`

### `GET /api/jobs/health`
Health check endpoint.

**Response**
```json
{"status": "ok"}
```

### `POST /api/jobs/scan-folder`
Validates a folder and scans for supported image files.

**Request body**
```json
{
  "folder_path": "/path/to/images"
}
```

**Response fields**
- `valid` (bool): whether folder is usable and contains supported images.
- `image_count` (int): number of supported files found.
- `sample_files` (list[str]): up to 5 sorted sample filenames.
- `estimated_pages` (int): `image_count // 12` (whole pages only).
- `message` (str): summary or error detail.

### `POST /api/jobs/scan-selected-batch-folders`
Validates selected batch subfolders under a scanned parent folder and reports which selected folders are ready for generation.

**Request body**
```json
{
  "parent_folder_path": "/path/to/parent-folder",
  "selected_subfolders": ["/path/to/parent-folder/bundle-a", "/path/to/parent-folder/bundle-b"]
}
```

**Response fields**
- `parent_folder_path` (str): normalized parent folder path.
- `selected_folders` (int): selected subfolders submitted for validation.
- `valid_selected_folders` (int): selected subfolders with eligible top-level images.
- `invalid_selected_folders` (int): selected subfolders skipped because they are invalid or not ready.
- `scanned_folders` (list): per-folder scan summaries for valid selected folders, including image counts and samples.
- `skipped_folders` (list): per-folder scan summaries for selected folders that were skipped or invalid.
- `message` (str): validation summary.

### `POST /api/jobs/generate`
Used by the UI when **Single folder** mode is selected. Scans one folder, composes pages with a fixed 4x3 layout, and exports files.

**Request body**
```json
{
  "folder_path": "/path/to/images",
  "output_path": "/path/to/output",
  "page_width": 3000,
  "page_height": 4000,
  "gap": 30,
  "margin": 60,
  "format": "PNG",
  "page_unit": "px",
  "dpi": 300,
  "background_clean_mode": "off",
  "background_tolerance": 240,
  "background_feather": 1,
  "include_partial_page": false
}
```

**Output quality fields** (shared by `/generate`, `/generate-all-folders`,
`/generate-cover-collage` and `/generate-cover-collage-batch`)
- `page_unit` (`px` | `in` | `mm`): unit for `page_width`/`page_height`. Anything
  other than `px` is converted to pixels at `dpi`, so `10 x 8 in` at `300` becomes
  `3000 x 2400 px`.
- `dpi` (int, 1-1200, default `300`): stamped into the exported file. Without it a
  `3000x4000` page carries no resolution and print software reads it at 72 DPI —
  41.7 x 55.6 in instead of 10 x 13.3 in.
- `background_clean_mode` (`off` | `flatten` | `transparent`, default `off`):
  cleans a near-white background off each image before it is placed. Only pixels
  **connected to the image border** are affected, so a white highlight inside the
  subject is left alone.
- `background_tolerance` (int, 0-255, default `240`): the lowest channel value
  counted as background. Lower catches more; too low starts eating the subject.
- `background_feather` (int, 0-25, default `1`): softens the mask edge, removing
  the grey halo around anti-aliased cut-outs.
- `include_partial_page` (bool, default `false`, grid endpoints only): render a
  final page even when it is not completely filled.
- Pages are capped at 100 megapixels after unit conversion (a 24 x 36 in poster
  at 300 DPI is 78 MP); a larger request is refused with a message saying so.

**Preview video fields** (`/generate` and `/generate-all-folders`)
- `create_video` (bool, default `false`; alias `create_preview_video`): also
  write an MP4 slideshow of the generated pages.
- `video_duration_seconds` (number, over 0 and at most `120`, default `15`;
  alias `duration_seconds`): the video runs exactly this long. Etsy's listing
  videos max out at 15 s.
- `video_transition` (`none` | `crossfade` | `flip`, default `none`; alias
  `transition`): transitions last 0.5 s, less when pages are short.
- `video_filename` (default `preview.mp4`): a plain `.mp4` file name, written
  into the output folder. Paths are refused.

The video is encoded at 30 fps and scaled to at most 1920 px on its long side
(never scaled up). If ffmpeg is missing or fails, the pages are still exported
and the response message gives ffmpeg's error.

**Response fields**
- `success` (bool)
- `total_images` (int): images actually placed
- `pages_generated` (int)
- `output_files` (list[str]): generated file paths
- `output_path` (str): normalized output folder path
- `images_dropped` (int): trailing images left out because they did not fill a page
- `backgrounds_cleaned` (int): images whose background was cleaned
- `page_geometry` (str): resolved page size, e.g. `3000x2400px (10.00x8.00in at 300 DPI)`
- `video_file` (str | null), `video_created` (bool): the preview video, when requested
- `message` (str): generation summary

### `POST /api/jobs/generate-all-folders`
Used by the UI when **Batch folders** mode is selected. Iterates bundle folders under a parent folder and writes each folder's generated pages under a created output root.

**Request body**
```json
{
  "parent_folder_path": "/path/to/parent-folder",
  "created_output_root_path": "/path/to/created-output-root",
  "page_width": 3000,
  "page_height": 4000,
  "gap": 30,
  "margin": 60,
  "format": "PNG",
  "selected_subfolders": ["/path/to/parent-folder/bundle-a", "/path/to/parent-folder/bundle-b"]
}
```

**Response fields**
- `success` (bool)
- `created_output_root_path` (str): normalized created output root
- `processed_folders` (int): selected bundle folders processed (kept for compatibility)
- `selected_folders` (int): selected bundle folders requested for generation
- `total_detected_folders` (int): eligible child folders detected under the parent folder
- `generated_folders` (int): bundle folders that produced pages
- `bundle_results` (list): per-folder generation summaries
- `message` (str): batch generation summary

---

## Sample UX Flow
1. Open `/` in browser.
2. Choose **Single folder** or **Batch folders** from the mode selector near the generation controls.
3. Enter the path fields using the labels shown for the selected mode:
   - **Single folder**: `Input folder` + `Output folder`
   - **Batch folders**: `Parent folder` + `Created output folder`
4. (Optional) Adjust page settings (`width`, `height`, `units`, `DPI`, `gap`,
   `margin`, `format`), and the background-cleaning controls if your source
   images sit on an off-white background.
5. Click **Scan folder** to validate the current input path.
   - Confirm `valid: true`, image count, and estimated pages.
6. Click **Generate pages** to call the endpoint for the selected mode:
   - **Single folder** → `POST /api/jobs/generate`
   - **Batch folders** → `POST /api/jobs/generate-all-folders`
7. Click **Cover collage** only when you want the separate `POST /api/jobs/generate-cover-collage` action for a single folder.
8. Review the output directory for generated `page_###.png` or `page_###.jpg` files.

---

## Known Constraints
- Layout is fixed to **4 columns x 3 rows** (12 images per page) only.
- No custom row/column configuration in MVP.
- Scan is non-recursive.
- Trailing images that do not fill a complete page are left out by default; the
  response reports how many. Set `include_partial_page: true` to render that final
  page with its unused cells left white.

---

## Acceptance Checklist (MVP Scope)
- [ ] App runs locally with FastAPI and serves UI.
- [ ] Folder scan validates path and reports supported image count.
- [ ] Supported file types: JPG/JPEG/PNG/WEBP.
- [ ] Estimated pages computed using fixed 12 images/page.
- [ ] Generation creates fixed 4x3 grids with centered, aspect-preserving fit.
- [ ] Transparent PNGs composite onto white rather than black.
- [ ] Exports carry DPI metadata so the page has a real physical size.
- [ ] Background cleaning only touches near-white areas connected to the border.
- [ ] Output exports as PNG or JPG.
- [ ] Exports use sequential naming (`page_###`) and avoid overwriting existing files.
- [ ] API returns clear success/error messages for scan and generation.
- [ ] UI supports end-to-end flow: input paths → scan → generate.

---

## Troubleshooting

### Transparent PNGs used to come out with a black background
Fixed. Transparent areas are composited onto the page's white rather than having
the alpha channel dropped, which is what left `(0, 0, 0)` showing through. This
covers RGBA, greyscale+alpha and palette PNGs carrying a `transparency` entry.

### The exported page opens at the wrong physical size
Check `dpi`. A page with no resolution metadata is read at 72 DPI, so a
`3000x4000` export measures 41.7 x 55.6 in instead of 10 x 13.3 in. Exports now
carry `dpi` (default 300); set `page_unit` to `in` or `mm` to give the page size
in physical units directly.

### Background cleaning did nothing
The image's border has to read as near-white before anything is cleaned — a
full-bleed photograph has no background to remove, and is returned untouched
rather than partially eaten. Lower `background_tolerance` for a greyer
background, or check the response message, which says which case applied.

### Background cleaning ate part of the subject
Raise `background_tolerance`. Note that only pixels connected to the border are
ever cleaned, so an enclosed light area (the inside of a ring, a white label on a
dark product) is safe regardless of tolerance.

### The preview video was not created
The pages are still exported; the response message gives the reason in
ffmpeg's own words. The usual cause is ffmpeg missing from `PATH` (install it,
then restart the app so it is found).

### Generation fails with "Computed cell size is invalid"
The margin and gaps leave no room for a 4x3 grid on the page. Reduce `margin`
or `gap`, or enlarge the page.

### Some images are missing from the output
Trailing images that do not fill a complete 12-image page are left out by
default. The response's `images_dropped` says how many; set
`include_partial_page: true` to render them on a final, partly-filled page.

### Invalid folder path
Symptoms:
- Scan response has `valid: false`
- Message such as:
  - `Invalid folder path.`
  - `Folder does not exist: ...`
  - `Path is not a folder: ...`

Fixes:
- Confirm absolute path is correct.
- Ensure the path exists on the same machine running the app.
- Use a directory path, not a file path.

### Empty scan results
Symptoms:
- `valid: false`
- `image_count: 0`
- Message: `No supported image files found (.jpg, .jpeg, .png, .webp).`

Fixes:
- Confirm files are directly in the selected folder (non-recursive scan).
- Confirm extensions are supported.
- Check that files are not hidden/system placeholders.

### Permission errors
Symptoms:
- Scan/generate fails when reading input files or writing output files.
- Some unreadable images are skipped during generation.

Fixes:
- Verify read permission on input folder and files.
- Verify write permission on output folder.
- Try a user-owned directory (for example inside your home directory).

---

## License
Apache License 2.0, see [LICENSE](LICENSE). Security reports: see
[SECURITY.md](SECURITY.md).
