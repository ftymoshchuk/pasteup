import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from pasteup import __version__
from pasteup.models.schemas import (
    BatchBundleResult,
    BatchCoverCollageGenerationRequest,
    BatchCoverCollageGenerationResponse,
    BatchCoverCollageResult,
    BatchGenerationRequest,
    BatchGenerationResponse,
    BrowseFolderRequest,
    BrowseFolderResponse,
    CoverCollageGenerationRequest,
    CoverCollageResponse,
    GenerationRequest,
    GenerationResponse,
    ScanRequest,
    ScanResponse,
    SelectedBatchFolderScanResult,
    SelectedBatchFolderValidationRequest,
    SelectedBatchFolderValidationResponse,
)
from pasteup.services.cover_collage import compose_cover_collage
from mullion import DEFAULT_TOLERANCE, BackgroundCleanMode
from pasteup.services.exporter import export_pages
from pasteup.services.folder_browser import browse_folder
from mullion import (
    DEFAULT_DPI,
    PageGeometry,
    resolve_page_geometry,
)
from pasteup.services.folder_scanner import (
    is_generated_output_folder,
    is_ignored_folder,
    list_supported_image_paths,
    resolve_folder_path,
    scan_folder,
)
from pasteup.services.grid_composer import compose_image_grids
from pasteup.services.video_exporter import build_preview_video

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Every page of a run is composed in memory, as RGB, before any is exported.
# 100 megapixels (~300 MB a page) still covers a 24x36in poster at 300 DPI; past
# it, a typo or a unit mix-up asks for tens of gigabytes and kills the process.
MAX_PAGE_MEGAPIXELS = 100


@dataclass(frozen=True, slots=True)
class _OutputOptions:
    """The print/cleanup options a page-producing request carries.

    Threaded as one object so adding a sixth option later does not mean editing
    four call chains — the drift this codebase is otherwise prone to.
    """

    dpi: int = DEFAULT_DPI
    page_unit: str = "px"
    background_clean_mode: BackgroundCleanMode = BackgroundCleanMode.OFF
    background_tolerance: int = DEFAULT_TOLERANCE
    background_feather: int = 1

    @classmethod
    def from_payload(cls, payload) -> "_OutputOptions":
        return cls(
            dpi=getattr(payload, "dpi", DEFAULT_DPI),
            page_unit=getattr(payload, "page_unit", "px"),
            background_clean_mode=getattr(
                payload, "background_clean_mode", BackgroundCleanMode.OFF
            ),
            background_tolerance=getattr(payload, "background_tolerance", DEFAULT_TOLERANCE),
            background_feather=getattr(payload, "background_feather", 1),
        )

    def geometry(self, *, page_width: float, page_height: float) -> PageGeometry:
        if not (math.isfinite(page_width) and math.isfinite(page_height)):
            raise ValueError("Page width and height must be finite numbers.")

        geometry = resolve_page_geometry(
            page_width=page_width,
            page_height=page_height,
            unit=self.page_unit,
            dpi=self.dpi,
        )
        megapixels = geometry.width_px * geometry.height_px / 1_000_000
        if megapixels > MAX_PAGE_MEGAPIXELS:
            raise ValueError(
                f"Page is {geometry.width_px}x{geometry.height_px}px ({megapixels:,.0f} MP); "
                f"the limit is {MAX_PAGE_MEGAPIXELS} MP. Reduce the page size or DPI."
            )
        return geometry


@router.get("/health")
def health_check() -> dict[str, str]:
    # "app" lets `pasteup` tell a running Pasteup from another program on its port.
    return {"status": "ok", "app": "pasteup", "version": __version__}


@router.post("/scan-folder", response_model=ScanResponse)
def scan_folder_job(payload: ScanRequest) -> ScanResponse:
    try:
        scan_result = scan_folder(payload.folder_path)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid folder path.") from exc
    except OSError as exc:
        return ScanResponse(
            valid=False,
            image_count=0,
            sample_files=[],
            estimated_pages=0,
            available_subfolders=[],
            message=f"Unable to access folder: {exc}",
    )

    return ScanResponse(**scan_result)


@router.post("/browse-folder", response_model=BrowseFolderResponse)
def browse_folder_job(payload: BrowseFolderRequest) -> BrowseFolderResponse:
    return BrowseFolderResponse(**browse_folder(payload.folder_path))


@router.post("/scan-selected-batch-folders", response_model=SelectedBatchFolderValidationResponse)
def scan_selected_batch_folders_job(
    payload: SelectedBatchFolderValidationRequest,
) -> SelectedBatchFolderValidationResponse:
    parent_folder = resolve_folder_path(payload.parent_folder_path)

    if not parent_folder.exists() or not parent_folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Invalid parent folder: {parent_folder}")

    discovered_bundle_folders = _list_detected_bundle_folders(
        parent_folder=parent_folder,
        created_root_name=None,
    )
    bundle_folder_lookup = {str(path): path for path in discovered_bundle_folders}
    selected_bundle_folders = _resolve_selected_bundle_folders(
        parent_folder=parent_folder,
        selected_subfolders=payload.selected_subfolders,
        bundle_folder_lookup=bundle_folder_lookup,
    )

    scanned_folders: list[SelectedBatchFolderScanResult] = []
    skipped_folders: list[SelectedBatchFolderScanResult] = []

    for selected_folder in selected_bundle_folders:
        scan_result = scan_folder(str(selected_folder))
        folder_result = SelectedBatchFolderScanResult(
            display_name=selected_folder.name,
            full_path=str(selected_folder),
            valid=bool(scan_result["valid"]),
            image_count=int(scan_result["image_count"]),
            sample_files=list(scan_result["sample_files"]),
            estimated_pages=int(scan_result["estimated_pages"]),
            message=str(scan_result["message"]),
        )

        if folder_result.valid:
            scanned_folders.append(folder_result)
        else:
            skipped_folders.append(folder_result)

    selected_folders = len(selected_bundle_folders)
    valid_selected_folders = len(scanned_folders)
    invalid_selected_folders = len(skipped_folders)

    return SelectedBatchFolderValidationResponse(
        parent_folder_path=str(parent_folder),
        selected_folders=selected_folders,
        valid_selected_folders=valid_selected_folders,
        invalid_selected_folders=invalid_selected_folders,
        scanned_folders=scanned_folders,
        skipped_folders=skipped_folders,
        message=(
            f"Validated {valid_selected_folders} of {selected_folders} selected folder(s). "
            f"Skipped {invalid_selected_folders} folder(s)."
        ),
    )


@router.post("/generate", response_model=GenerationResponse)
def generate_job(payload: GenerationRequest):
    return _generate_for_single_folder(
        folder_path=payload.folder_path,
        output_path=payload.output_path,
        page_width=payload.page_width,
        page_height=payload.page_height,
        margin=payload.margin,
        gap=payload.gap,
        export_format=payload.format,
        create_video=payload.create_video,
        video_duration_seconds=payload.video_duration_seconds,
        video_transition=payload.video_transition,
        video_filename=payload.video_filename,
        include_partial_page=payload.include_partial_page,
        options=_OutputOptions.from_payload(payload),
    )


@router.post("/generate-cover-collage", response_model=CoverCollageResponse)
def generate_cover_collage_job(payload: CoverCollageGenerationRequest) -> CoverCollageResponse:
    response = _generate_cover_collage_for_single_folder(
        folder_path=payload.folder_path,
        output_path=payload.output_path,
        page_width=payload.page_width,
        page_height=payload.page_height,
        export_format=payload.format,
        collage_template=payload.collage_template,
        image_fit=payload.image_fit,
        selected_cover_images=payload.selected_cover_images,
        options=_OutputOptions.from_payload(payload),
    )
    if isinstance(response, JSONResponse):
        content = json.loads(response.body.decode("utf-8"))
        raise HTTPException(status_code=response.status_code, detail=content.get("message", "Unable to generate cover collage."))
    return response




@router.post("/generate-cover-collage-batch", response_model=BatchCoverCollageGenerationResponse)
def generate_cover_collage_batch_job(
    payload: BatchCoverCollageGenerationRequest,
) -> BatchCoverCollageGenerationResponse:
    parent_folder = resolve_folder_path(payload.parent_folder_path)
    created_root = Path(payload.created_output_root_path).expanduser()

    if not parent_folder.exists() or not parent_folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Invalid parent folder: {parent_folder}")

    discovered_bundle_folders = _list_detected_bundle_folders(
        parent_folder=parent_folder,
        created_root_name=created_root.name,
    )
    bundle_folder_lookup = {str(path): path for path in discovered_bundle_folders}
    bundle_folders = _resolve_selected_bundle_folders(
        parent_folder=parent_folder,
        selected_subfolders=payload.selected_subfolders,
        bundle_folder_lookup=bundle_folder_lookup,
    )

    total_detected_folders = len(discovered_bundle_folders)
    selected_folders = len(bundle_folders)

    bundle_results = [
        _generate_cover_collage_batch_result(
            bundle_folder=bundle_folder,
            created_root=created_root,
            page_width=payload.page_width,
            page_height=payload.page_height,
            export_format=payload.format,
            collage_template=payload.collage_template,
            image_fit=payload.image_fit,
            options=_OutputOptions.from_payload(payload),
        )
        for bundle_folder in bundle_folders
    ]
    generated_folders = sum(1 for result in bundle_results if result.success and result.pages_generated > 0)

    return BatchCoverCollageGenerationResponse(
        success=True,
        processed_folders=selected_folders,
        generated_folders=generated_folders,
        total_detected_folders=total_detected_folders,
        selected_folders=selected_folders,
        bundle_results=bundle_results,
        created_output_root_path=str(created_root),
        message=(
            f"Detected {total_detected_folders} eligible folder(s) under the parent. "
            f"Processed {selected_folders} selected folder(s). "
            f"Generated cover collages for {generated_folders} folder(s)."
        ),
    )


@router.post("/generate-all-folders", response_model=BatchGenerationResponse)
def generate_all_folders_job(payload: BatchGenerationRequest) -> BatchGenerationResponse:
    parent_folder = resolve_folder_path(payload.parent_folder_path)
    created_root = Path(payload.created_output_root_path).expanduser()

    if not parent_folder.exists() or not parent_folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Invalid parent folder: {parent_folder}")

    discovered_bundle_folders = _list_detected_bundle_folders(
        parent_folder=parent_folder,
        created_root_name=created_root.name,
    )
    bundle_folder_lookup = {str(path): path for path in discovered_bundle_folders}

    if payload.selected_subfolders is None:
        bundle_folders = discovered_bundle_folders
    else:
        bundle_folders = _resolve_selected_bundle_folders(
            parent_folder=parent_folder,
            selected_subfolders=payload.selected_subfolders,
            bundle_folder_lookup=bundle_folder_lookup,
        )

    total_detected_folders = len(discovered_bundle_folders)
    selected_folders = len(bundle_folders)

    bundle_results: list[BatchBundleResult] = []
    generated_folders = 0

    for bundle_folder in bundle_folders:
        bundle_output = _build_batch_bundle_output_path(
            created_root=created_root,
            bundle_folder=bundle_folder,
        )
        generation_response = _generate_for_single_folder(
            folder_path=str(bundle_folder),
            output_path=str(bundle_output),
            page_width=payload.page_width,
            page_height=payload.page_height,
            margin=payload.margin,
            gap=payload.gap,
            export_format=payload.format,
            create_video=payload.create_video,
            video_duration_seconds=payload.video_duration_seconds,
            video_transition=payload.video_transition,
            video_filename=payload.video_filename,
            include_partial_page=payload.include_partial_page,
            options=_OutputOptions.from_payload(payload),
        )

        if isinstance(generation_response, JSONResponse):
            content = json.loads(generation_response.body.decode("utf-8"))
            bundle_results.append(
                BatchBundleResult(
                    folder_name=bundle_folder.name,
                    success=False,
                    pages_generated=0,
                    total_images=0,
                    output_path=str(bundle_output),
                    video_file=None,
                    video_created=False,
                    message=str(content.get("message", "Unable to generate folder.")),
                )
            )
            continue

        if generation_response.pages_generated > 0:
            generated_folders += 1

        bundle_results.append(
            BatchBundleResult(
                folder_name=bundle_folder.name,
                success=generation_response.success,
                pages_generated=generation_response.pages_generated,
                total_images=generation_response.total_images,
                output_path=generation_response.output_path,
                video_file=generation_response.video_file,
                video_created=generation_response.video_created,
                message=generation_response.message,
            )
        )

    return BatchGenerationResponse(
        success=True,
        processed_folders=selected_folders,
        generated_folders=generated_folders,
        total_detected_folders=total_detected_folders,
        selected_folders=selected_folders,
        bundle_results=bundle_results,
        created_output_root_path=str(created_root),
        message=(
            f"Detected {total_detected_folders} eligible folder(s) under the parent. "
            f"Processed {selected_folders} selected folder(s). "
            f"Generated collage pages for {generated_folders} folder(s)."
        ),
    )




def _generate_cover_collage_batch_result(
    *,
    bundle_folder: Path,
    created_root: Path,
    page_width: float,
    page_height: float,
    export_format: str,
    collage_template,
    image_fit,
    options: _OutputOptions | None = None,
) -> BatchCoverCollageResult:
    bundle_output = _build_batch_bundle_output_path(
        created_root=created_root,
        bundle_folder=bundle_folder,
    )
    generation_response = _generate_cover_collage_for_single_folder(
        folder_path=str(bundle_folder),
        output_path=str(bundle_output),
        page_width=page_width,
        page_height=page_height,
        export_format=export_format,
        collage_template=collage_template,
        image_fit=image_fit,
        options=options,
    )

    if isinstance(generation_response, JSONResponse):
        content = json.loads(generation_response.body.decode("utf-8"))
        return BatchCoverCollageResult(
            folder_name=bundle_folder.name,
            success=False,
            pages_generated=0,
            total_images=0,
            output_path=str(bundle_output),
            output_files=[],
            message=str(content.get("message", "Unable to generate cover collage.")),
        )

    return BatchCoverCollageResult(
        folder_name=bundle_folder.name,
        success=generation_response.success,
        pages_generated=generation_response.pages_generated,
        total_images=generation_response.total_images,
        output_path=generation_response.output_path,
        output_files=generation_response.output_files,
        message=generation_response.message,
    )


def _generate_cover_collage_for_single_folder(
    *,
    folder_path: str,
    output_path: str,
    page_width: float,
    page_height: float,
    export_format: str,
    collage_template,
    image_fit,
    selected_cover_images: list[str] | None = None,
    options: _OutputOptions | None = None,
):
    resolved_options = options or _OutputOptions()
    try:
        geometry = resolved_options.geometry(page_width=page_width, page_height=page_height)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"message": str(exc)})

    try:
        input_folder = resolve_folder_path(folder_path)
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"message": "Invalid folder path."},
        )

    if not input_folder.exists():
        return JSONResponse(status_code=400, content={"message": f"Folder not found: {input_folder}"})
    if not input_folder.is_dir():
        return JSONResponse(status_code=400, content={"message": f"Path is not a folder: {input_folder}"})

    image_paths = [str(path) for path in list_supported_image_paths(input_folder, recursive=True)]
    if not image_paths:
        return JSONResponse(
            status_code=400,
            content={"message": "No supported image files found (.jpg, .jpeg, .png, .webp)."},
        )

    if selected_cover_images is not None:
        selected_cover_image_names = set(selected_cover_images)
        image_paths = [
            image_path for image_path in image_paths if Path(image_path).name in selected_cover_image_names
        ]
        if not image_paths:
            return JSONResponse(
                status_code=400,
                content={
                    "message": (
                        "Cover collage include list did not match any supported images in the selected folder. "
                        "Use exact filenames, including extensions."
                    )
                },
            )

    pages, summary = compose_cover_collage(
        image_paths,
        page_width=geometry.width_px,
        page_height=geometry.height_px,
        template=collage_template,
        fitting_mode=image_fit,
        background_clean_mode=resolved_options.background_clean_mode,
        background_tolerance=resolved_options.background_tolerance,
        background_feather=resolved_options.background_feather,
    )
    output_files = export_pages(
        pages,
        output_path,
        export_format,
        filename_prefix="cover_collage",
        dpi=geometry.dpi,
    )

    return CoverCollageResponse(
        success=bool(output_files),
        total_images=summary.total_images_placed,
        pages_generated=len(output_files),
        output_files=output_files,
        output_path=str(Path(output_path).expanduser()),
        page_geometry=geometry.description,
        message=summary.user_message,
    )

def _generate_for_single_folder(
    *,
    folder_path: str,
    output_path: str,
    page_width: float,
    page_height: float,
    margin: float,
    gap: float,
    export_format: str,
    create_video: bool = False,
    video_duration_seconds: float = 15.0,
    video_transition: Literal["none", "crossfade", "flip"] = "none",
    video_filename: str = "preview.mp4",
    include_partial_page: bool = False,
    options: _OutputOptions | None = None,
):
    resolved_options = options or _OutputOptions()
    try:
        geometry = resolved_options.geometry(page_width=page_width, page_height=page_height)
    except ValueError as exc:
        return _generation_error(output_path=output_path, message=str(exc))

    scan_result = scan_folder(folder_path)
    if not scan_result["valid"]:
        return _generation_error(output_path=output_path, message=str(scan_result["message"]))

    input_folder = Path(folder_path).expanduser()
    image_paths = [str(path) for path in list_supported_image_paths(input_folder)]

    # Every path goes to the composer, which decides what to do with a trailing
    # remainder. Truncating here with build_image_batches would hide the
    # remainder from it, so the summary could not report what was left out --
    # which is the silent data loss this reporting exists to remove. The page
    # output is identical either way when include_partial_page is off.
    try:
        pages, compose_summary = compose_image_grids(
            image_paths,
            page_width=geometry.width_px,
            page_height=geometry.height_px,
            margin=margin,
            gap=gap,
            background_clean_mode=resolved_options.background_clean_mode,
            background_tolerance=resolved_options.background_tolerance,
            background_feather=resolved_options.background_feather,
            include_partial_page=include_partial_page,
        )
    except ValueError as exc:
        # Settings that leave no room for a cell, such as a margin wider than
        # half the page. Reported as the user's to fix, not as a server fault.
        return _generation_error(output_path=output_path, message=str(exc))
    output_files = export_pages(pages, output_path, export_format, dpi=geometry.dpi)
    video_file: str | None = None
    video_created = False
    video_status_message: str | None = None
    if create_video and output_files:
        requested_video_path = str((Path(output_path).expanduser() / video_filename).resolve())
        try:
            video_file = build_preview_video(
                page_paths=output_files,
                output_dir=output_path,
                duration_seconds=video_duration_seconds,
                transition=video_transition,
                filename=video_filename,
            )
            video_status_message = f"Preview video saved to: {video_file}"
        except (RuntimeError, ValueError) as exc:
            video_file = None
            video_status_message = (
                f"Preview video was requested but could not be created ({exc}). "
                f"Expected output path: {requested_video_path}."
            )

        video_created = video_file is not None

    response_message = compose_summary.user_message
    if video_status_message:
        response_message = f"{response_message} {video_status_message}"

    return GenerationResponse(
        success=True,
        total_images=compose_summary.total_images_placed,
        pages_generated=len(output_files),
        output_files=output_files,
        output_path=str(Path(output_path).expanduser()),
        video_file=video_file,
        video_created=video_created,
        images_dropped=compose_summary.total_images_dropped,
        images_skipped=compose_summary.total_images_skipped,
        backgrounds_cleaned=compose_summary.background_cleaned,
        page_geometry=geometry.description,
        message=response_message,
    )


def _generation_error(*, output_path: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=GenerationResponse(
            success=False,
            total_images=0,
            pages_generated=0,
            output_files=[],
            output_path=output_path,
            video_file=None,
            video_created=False,
            message=message,
        ).model_dump(),
    )


def _resolve_selected_bundle_folders(
    *,
    parent_folder: Path,
    selected_subfolders: list[str],
    bundle_folder_lookup: dict[str, Path],
) -> list[Path]:
    resolved_bundle_folders: list[Path] = []

    for selected_path in selected_subfolders:
        candidate_folder = resolve_folder_path(selected_path)

        try:
            candidate_folder.relative_to(parent_folder)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Selected folder is not inside the scanned parent folder: {candidate_folder}",
            ) from exc

        if not candidate_folder.exists() or not candidate_folder.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"Selected folder does not exist or is not a directory: {candidate_folder}",
            )

        if is_generated_output_folder(candidate_folder):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Selected folder points to a generated-output directory and cannot be "
                    f"used as a source folder: {candidate_folder}"
                ),
            )

        matched_folder = bundle_folder_lookup.get(str(candidate_folder))
        if matched_folder is None:
            raise HTTPException(
                status_code=400,
                detail=f"Selected folder was not part of the detected child folders: {candidate_folder}",
            )

        resolved_bundle_folders.append(matched_folder)

    return resolved_bundle_folders


def _build_batch_bundle_output_path(*, created_root: Path, bundle_folder: Path) -> Path:
    """Mirror batch page-generation outputs under `<created root>/<source folder name>`."""
    return created_root / bundle_folder.name


def _list_detected_bundle_folders(*, parent_folder: Path, created_root_name: str | None) -> list[Path]:
    return sorted(
        [
            item.resolve(strict=False)
            for item in parent_folder.iterdir()
            if item.is_dir()
            and item.name != created_root_name
            and not is_ignored_folder(item)
        ],
        key=lambda path: (path.name.lower(), path.name),
    )
