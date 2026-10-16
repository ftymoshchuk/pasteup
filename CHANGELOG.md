# Changelog

All notable changes to Pasteup are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). While Pasteup is
0.x, a minor version may change behaviour.

## [Unreleased]

### Added
- **Browse…** beside the folder field opens a folder browser, so a folder can be
  picked instead of typed. It opens at the folder in the field, or at your home
  folder, says how many images the folder you're in holds, and scans the one
  you choose. Typing or pasting a path still works.
  (`POST /api/jobs/browse-folder`)
- Upscaled images, from a tile of their own in step 3: every image of a bundle,
  or of each picked bundle, made 2x, 3x or 4x bigger and saved in an
  `Upscaled` folder as a PNG, which keeps any transparency, and a JPG on
  white. (`POST /api/jobs/upscale-images`, `POST /api/jobs/upscale-images-batch`)

### Fixed
- Hidden files are no longer counted as images. A Mac writes a hidden `._`
  file beside the files it copies to an exFAT or FAT32 drive or to some network
  shares, so such a bundle could scan as twice its size, and making sheets then
  reported the extra files as unreadable.
- Hidden folders, such as the `.Spotlight-V100` and `.Trashes` a Mac keeps on
  those drives, and the `__MACOSX` folder left by unpacking a zip made on a
  Mac, are no longer offered as bundles. Covers no longer take images from
  them, nor from a `---Created---` folder inside the bundle.
- After a scan or making images, keyboard focus returns to the button that
  started it, instead of falling back to the top of the page.

## [0.1.0] - 2026-10-16

The first release on PyPI.

### Added
- Preview sheets: every image of a bundle in 4x3 grids on a white page, as PNG
  or JPG, sized in pixels, inches or millimetres, with the DPI stamped into
  the file. A part-filled last page is optional.
- Cover collages in three layouts, optionally limited to images you name.
- Preview videos: an MP4 slideshow of the sheets, as long as you ask, with a
  crossfade or flip between them. Needs ffmpeg.
- Batch mode: every bundle folder inside a folder, listed, checked and made in
  one go.
- Image clean-up: transparent PNGs land on white, phone photos are turned
  upright, and near-white backgrounds can be made pure white or transparent.
- A hand-drawn browser interface in three steps, with each result beside the
  step that made it. It runs entirely on your computer and needs no internet
  connection.
- The `pasteup` command opens the app in your browser, reuses a copy that is
  already running and moves to a free port when another program has 8000.
  `pasteup --shortcut` makes a double-click launcher.

[Unreleased]: https://github.com/ftymoshchuk/pasteup/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ftymoshchuk/pasteup/releases/tag/v0.1.0
