# Pasteup

Turn a folder of clip art into listing images: preview sheets, a cover collage
and a short preview video, ready for Etsy and other marketplaces. Pasteup runs
on your own computer and works in your browser.

The name comes from *paste-up*, how clip art was used before desktop
publishing: cut out by hand and pasted onto a layout board.

## What it does
- **Preview sheets:** 4x3 grids of your images on a white page, as PNG or JPG
  at a chosen DPI.
- **Cover collage:** a single page in one of three layouts, for a listing's
  main image.
- **Preview video:** an MP4 slideshow of the sheets, exactly as long as you ask
  (Etsy's listing videos run 5 to 15 s).
- **Clean-up:** transparent PNGs land on white instead of black, phone photos
  are turned upright, and near-white backgrounds can be removed.
- **Batch mode:** process every bundle folder under a parent folder in one go.

## Install
You need Python 3.11 or newer. Preview videos also need
[ffmpeg](https://ffmpeg.org/download.html); everything else works without it.

Install Pasteup as a command of its own with [pipx](https://pipx.pypa.io) or
[uv](https://docs.astral.sh/uv/), with no virtualenv to manage:

```bash
pipx install git+https://github.com/ftymoshchuk/pasteup.git
# or
uv tool install git+https://github.com/ftymoshchuk/pasteup.git
```

To update it later: `pipx upgrade pasteup` or `uv tool upgrade pasteup`.

To try it without installing anything:
```bash
uvx --from git+https://github.com/ftymoshchuk/pasteup.git pasteup
```

## Run
```bash
pasteup
```
Pasteup starts and opens in your browser. Keep its window open while you use
it, and press Ctrl+C there to stop it. Running `pasteup` again while it runs
just opens it again, and if another program has port 8000, Pasteup takes the
next free port and says which.

**To start it with a double-click,** run `pasteup --shortcut` once. It puts a
launcher on your desktop (`Pasteup.command` on macOS, `Pasteup.bat` on
Windows) or in your applications menu on Linux. Run it again if you reinstall
Pasteup somewhere else.

`pasteup --help` lists the options, among them `--no-browser` and `--port`;
`python -m pasteup` works too. The API docs are at `/docs`.

Pasteup reads and writes files at the paths you give it and has no login, so
keep it on `127.0.0.1` (the default). See [SECURITY.md](SECURITY.md).

### Optional environment variables
- `PASTEUP_INPUT_FOLDER`: prefills the input-folder field, e.g.
  `PASTEUP_INPUT_FOLDER=~/Pictures/clip-art pasteup`.
- `PASTEUP_ALLOWED_HOSTS`: comma-separated host names to accept besides
  `localhost`, `127.0.0.1` and `[::1]`. Only for serving the app under another
  name on purpose.

## Development
```bash
git clone https://github.com/ftymoshchuk/pasteup.git
cd pasteup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
```
CI runs the same on Python 3.11 and 3.13, against a regular install of the
package and with ffmpeg present, so the preview-video tests encode real files.
Its `ci-passed` job succeeds only when every other job does, and is the one
check `main` requires.

`scripts/protect-repo.sh` applies the repository's branch ruleset and security
settings through the GitHub CLI; it needs `gh` signed in as a repository admin.

Project layout:
- `src/pasteup/main.py`: the FastAPI app
- `src/pasteup/routes/`: the page and the `/api/jobs` endpoints
- `src/pasteup/services/`: scanning, page composition, collages, export, video
- `src/pasteup/models/`: request and response schemas
- `src/pasteup/templates/` and `src/pasteup/static/`: the UI
- `src/pasteup/cli.py`: the `pasteup` command; `shortcut.py` makes its launchers
- `tests/`

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
- input folder: empty (set `PASTEUP_INPUT_FOLDER` to prefill it)
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
{"status": "ok", "app": "pasteup", "version": "0.1.0"}
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
Used by the UI in **One bundle** mode. Scans one folder, composes pages with a fixed 4x3 layout, and exports files.

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
Used by the UI in **Many bundles** mode. Iterates bundle folders under a parent folder and writes each folder's generated pages under a created output root.

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

## Using the app
1. Run `pasteup` and open `http://127.0.0.1:8000/`.
2. **Pick your clip art.** Choose **One bundle** (a folder of images) or **Many
   bundles** (a folder with one folder inside per bundle), enter the folder and
   click **Scan folder**. Results go in a `---Created---` folder next to it.
   - One bundle: **Folder check** says how many images it found and how many
     full sheets of 12 they make. If the folder holds only other folders, pick
     one under **Choose folders**.
   - Many bundles: every bundle inside is listed, picked and checked in one go.
     Untick any you want to skip. A bundle that fails its check can be unticked,
     or fixed and checked again with **Check selected bundles**.
3. **Set up the page.** Size, units, DPI and format apply to sheets and covers
   alike. **Clean up white backgrounds** can make near-white backgrounds pure
   white or transparent.
4. **Make your images.**
   - **Preview sheets:** every image, 12 to a page (`POST /api/jobs/generate`,
     or `POST /api/jobs/generate-all-folders` for many bundles), optionally with a
     part-filled last page and an MP4 preview video.
   - **Cover collage:** one cover in the chosen layout
     (`POST /api/jobs/generate-cover-collage`, or
     `POST /api/jobs/generate-cover-collage-batch`). **Only use certain images**
     limits it to the files you name.
5. **Your files** lists what was made and where it was saved; **Copy** puts a
   path on the clipboard.

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
`include_partial_page: true` (in the app, tick **Include a part-filled last
page**) to render them on a final, partly-filled page.

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

## How images are loaded
Opening, background cleaning and page geometry live in
[mullion](https://github.com/sigrix-io/mullion), a small library Pasteup
depends on (`mullion~=0.2.1`, from PyPI).

`mullion.open_path()` is the one place a source image is opened. It composites
transparency onto white (a bare `convert("RGB")` drops the alpha and leaves the
black underneath showing) and applies EXIF orientation, so a phone photo is not
placed sideways. `mullion.clean_background()` is the border-seeded cleaner
described above, and `mullion.resolve_page_geometry()` turns `page_unit` and
`dpi` into the pixel size the exporter stamps. mullion's own suite tests these
directly; Pasteup's tests check the same claims through its composer and
exporter, so a bad mullion upgrade still fails here.

---

## License
Apache License 2.0, see [LICENSE](LICENSE). Security reports: see
[SECURITY.md](SECURITY.md).

The handwriting fonts the app ships with, [Caveat](https://fonts.google.com/specimen/Caveat)
and [Patrick Hand](https://fonts.google.com/specimen/Patrick+Hand), are under the
SIL Open Font License 1.1; their licence texts are in
[src/pasteup/static/fonts](src/pasteup/static/fonts). They are bundled rather
than fetched, so the app needs no internet connection.
