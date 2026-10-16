from pathlib import Path
from typing import Literal

from mullion import DEFAULT_TOLERANCE, BackgroundCleanMode
from app.services.cover_collage import CoverCollageFittingMode, CoverCollageTemplate
from mullion import DEFAULT_DPI

from pydantic import AliasChoices, BaseModel, Field, field_validator

# The preview is encoded at a real frame rate, so its length sets the encoding
# work. Two minutes is well past any listing site's limit (Etsy's is 15 s).
MAX_VIDEO_DURATION_SECONDS = 120


def _normalize_optional_string_list(value: object, *, field_name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings.")

    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} must contain only strings.")
        normalized_item = item.strip()
        if not normalized_item or normalized_item in seen_values:
            continue
        seen_values.add(normalized_item)
        normalized_values.append(normalized_item)

    return normalized_values


def _validate_video_filename(value: str) -> str:
    """Keep the preview video inside the output folder.

    The name is joined onto the output folder and ffmpeg overwrites whatever is
    already there, so a path in it would let a request replace any file the user
    can write — ``/Users/me/notes.txt`` or ``../../anything.mp4`` alike.
    """
    name = value.strip()
    if name in {"", ".", ".."} or "\\" in name or Path(name).name != name:
        raise ValueError("video_filename must be a plain file name, without folders.")
    if Path(name).suffix.lower() != ".mp4":
        raise ValueError("video_filename must end in .mp4.")
    return name


class OutputQualityOptions(BaseModel):
    """Print-resolution and background-cleaning options.

    Shared by every request that produces a page, so the four builders cannot
    drift into supporting different subsets of the same feature.
    """

    dpi: int = Field(
        default=DEFAULT_DPI,
        gt=0,
        le=1200,
        description=(
            "Resolution stamped into exported files. Without it a 3000x4000 page "
            "reads as 41.7x55.6in at the 72 DPI default rather than 10x13.3in."
        ),
    )
    page_unit: Literal["px", "in", "mm"] = Field(
        default="px",
        description="Unit for page_width/page_height. Converted to pixels at dpi.",
    )
    background_clean_mode: BackgroundCleanMode = Field(
        default=BackgroundCleanMode.OFF,
        description=(
            "'flatten' turns an edge-connected near-white background pure white; "
            "'transparent' makes it transparent; 'off' leaves images untouched."
        ),
    )
    background_tolerance: int = Field(
        default=DEFAULT_TOLERANCE,
        ge=0,
        le=255,
        description="Minimum channel value counted as background. Higher is stricter.",
    )
    background_feather: int = Field(
        default=1,
        ge=0,
        le=25,
        description="Mask softening in pixels; removes halos on anti-aliased edges.",
    )

    @field_validator("background_clean_mode", mode="before")
    @classmethod
    def normalize_background_clean_mode(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class JobStatus(BaseModel):
    status: str


class ScanRequest(BaseModel):
    folder_path: str


class ScanSubfolder(BaseModel):
    display_name: str
    full_path: str


class ScanResponse(BaseModel):
    valid: bool
    image_count: int
    sample_files: list[str]
    estimated_pages: int
    available_subfolders: list[ScanSubfolder] = Field(default_factory=list)
    message: str


class SelectedBatchFolderValidationRequest(BaseModel):
    parent_folder_path: str
    selected_subfolders: list[str] = Field(
        validation_alias=AliasChoices("selected_subfolders", "selected_subfolder_paths"),
    )

    @field_validator("selected_subfolders", mode="before")
    @classmethod
    def normalize_selected_subfolders(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("selected_subfolders must be a list of paths.")

        normalized_paths: list[str] = []
        seen_paths: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("selected_subfolders must contain only strings.")
            normalized_item = item.strip()
            if not normalized_item or normalized_item in seen_paths:
                continue
            seen_paths.add(normalized_item)
            normalized_paths.append(normalized_item)

        return normalized_paths


class SelectedBatchFolderScanResult(BaseModel):
    display_name: str
    full_path: str
    valid: bool
    image_count: int
    sample_files: list[str]
    estimated_pages: int
    message: str


class SelectedBatchFolderValidationResponse(BaseModel):
    parent_folder_path: str
    selected_folders: int
    valid_selected_folders: int
    invalid_selected_folders: int
    scanned_folders: list[SelectedBatchFolderScanResult]
    skipped_folders: list[SelectedBatchFolderScanResult]
    message: str


class GenerationRequest(OutputQualityOptions):
    folder_path: str
    output_path: str
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    gap: float = Field(ge=0)
    margin: float = Field(ge=0)
    format: Literal["PNG", "JPG"]
    include_partial_page: bool = Field(
        default=False,
        description=(
            "Render a final page whose cells are not all filled. Off preserves the "
            "existing behaviour of leaving trailing images out; either way the count "
            "is reported rather than dropped silently."
        ),
    )
    create_video: bool = Field(
        default=False,
        validation_alias=AliasChoices("create_video", "create_preview_video"),
    )
    video_duration_seconds: float = Field(
        default=15.0,
        gt=0,
        le=MAX_VIDEO_DURATION_SECONDS,
        validation_alias=AliasChoices("video_duration_seconds", "duration_seconds"),
    )
    video_transition: Literal["none", "crossfade", "flip"] = Field(
        default="none",
        validation_alias=AliasChoices("video_transition", "transition"),
    )
    video_filename: str = "preview.mp4"

    @field_validator("format", mode="before")
    @classmethod
    def normalize_format(cls, value: str) -> str:
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("video_filename")
    @classmethod
    def validate_video_filename(cls, value: str) -> str:
        return _validate_video_filename(value)


class GenerationResponse(BaseModel):
    success: bool
    total_images: int
    pages_generated: int
    output_files: list[str]
    output_path: str
    video_file: str | None = None
    video_created: bool = False
    images_dropped: int = 0
    backgrounds_cleaned: int = 0
    page_geometry: str | None = None
    message: str


class CoverCollageGenerationRequest(OutputQualityOptions):
    folder_path: str
    output_path: str
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    format: Literal["PNG", "JPG"]
    collage_template: CoverCollageTemplate = CoverCollageTemplate.RANDOMIZED_GRID
    image_fit: CoverCollageFittingMode = CoverCollageFittingMode.COVER
    selected_cover_images: list[str] | None = None

    @field_validator("format", mode="before")
    @classmethod
    def normalize_format(cls, value: str) -> str:
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("selected_cover_images", mode="before")
    @classmethod
    def normalize_selected_cover_images(cls, value: object) -> list[str] | None:
        return _normalize_optional_string_list(value, field_name="selected_cover_images")


class CoverCollageResponse(BaseModel):
    success: bool
    total_images: int
    pages_generated: int
    output_files: list[str]
    output_path: str
    page_geometry: str | None = None
    message: str


class BatchCoverCollageGenerationRequest(OutputQualityOptions):
    parent_folder_path: str
    created_output_root_path: str = Field(
        validation_alias=AliasChoices("created_output_root_path", "output_root_path"),
    )
    selected_subfolders: list[str] = Field(
        validation_alias=AliasChoices("selected_subfolders", "selected_subfolder_paths"),
    )
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    format: Literal["PNG", "JPG"]
    collage_template: CoverCollageTemplate = CoverCollageTemplate.RANDOMIZED_GRID
    image_fit: CoverCollageFittingMode = CoverCollageFittingMode.COVER

    @field_validator("selected_subfolders", mode="before")
    @classmethod
    def normalize_selected_subfolders(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("selected_subfolders must be a list of paths.")

        normalized_paths: list[str] = []
        seen_paths: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("selected_subfolders must contain only strings.")
            normalized_item = item.strip()
            if not normalized_item or normalized_item in seen_paths:
                continue
            seen_paths.add(normalized_item)
            normalized_paths.append(normalized_item)

        return normalized_paths

    @field_validator("format", mode="before")
    @classmethod
    def normalize_format(cls, value: str) -> str:
        if isinstance(value, str):
            return value.upper()
        return value


class BatchCoverCollageResult(BaseModel):
    folder_name: str
    success: bool
    pages_generated: int
    total_images: int
    output_path: str
    output_files: list[str] = Field(default_factory=list)
    message: str


class BatchCoverCollageGenerationResponse(BaseModel):
    success: bool
    processed_folders: int
    generated_folders: int
    total_detected_folders: int
    selected_folders: int
    bundle_results: list[BatchCoverCollageResult]
    created_output_root_path: str
    message: str


class BatchGenerationRequest(OutputQualityOptions):
    parent_folder_path: str
    created_output_root_path: str
    selected_subfolders: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("selected_subfolders", "selected_subfolder_paths"),
    )
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    gap: float = Field(ge=0)
    margin: float = Field(ge=0)
    format: Literal["PNG", "JPG"]
    include_partial_page: bool = Field(
        default=False,
        description=(
            "Render a final page whose cells are not all filled. Off preserves the "
            "existing behaviour of leaving trailing images out; either way the count "
            "is reported rather than dropped silently."
        ),
    )
    create_video: bool = Field(
        default=False,
        validation_alias=AliasChoices("create_video", "create_preview_video"),
    )
    video_duration_seconds: float = Field(
        default=15.0,
        gt=0,
        le=MAX_VIDEO_DURATION_SECONDS,
        validation_alias=AliasChoices("video_duration_seconds", "duration_seconds"),
    )
    video_transition: Literal["none", "crossfade", "flip"] = Field(
        default="none",
        validation_alias=AliasChoices("video_transition", "transition"),
    )
    video_filename: str = "preview.mp4"

    @field_validator("selected_subfolders", mode="before")
    @classmethod
    def normalize_selected_subfolders(cls, value: object) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("selected_subfolders must be a list of paths.")

        normalized_paths: list[str] = []
        seen_paths: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("selected_subfolders must contain only strings.")
            normalized_item = item.strip()
            if not normalized_item or normalized_item in seen_paths:
                continue
            seen_paths.add(normalized_item)
            normalized_paths.append(normalized_item)

        return normalized_paths

    @field_validator("format", mode="before")
    @classmethod
    def normalize_format(cls, value: str) -> str:
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("video_filename")
    @classmethod
    def validate_video_filename(cls, value: str) -> str:
        return _validate_video_filename(value)


class BatchBundleResult(BaseModel):
    folder_name: str
    success: bool
    pages_generated: int
    total_images: int
    output_path: str
    video_file: str | None = None
    video_created: bool = False
    message: str


class BatchGenerationResponse(BaseModel):
    success: bool
    processed_folders: int
    generated_folders: int
    total_detected_folders: int
    selected_folders: int
    bundle_results: list[BatchBundleResult]
    created_output_root_path: str
    message: str
