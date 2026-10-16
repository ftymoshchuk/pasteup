import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_TEMPLATE = ROOT / "app" / "templates" / "index.html"
APP_JS = ROOT / "app" / "static" / "js" / "app.js"


def _squash_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def test_index_exposes_batch_validation_controls_and_copy() -> None:
    html = INDEX_TEMPLATE.read_text()
    normalized = _squash_whitespace(html)

    assert 'id="subfolder-picker-section"' in html
    assert 'id="batch-subfolder-checklist"' in html
    assert 'button id="select-all-subfolders-button"' in normalized
    assert 'button id="clear-subfolder-selection-button"' in normalized
    assert 'button id="batch-scan-button" class="primary-button terminal-button" type="button">Scan selected folders</button>' in normalized
    assert 'id="cover-collage-include-list"' in html
    assert "Cover collage include list" in html
    assert "one per line or comma-separated" in html
    assert 'Run the parent-folder scan, choose folders, then use Scan selected folders to validate the batch before page or cover-collage generation.' in normalized
    assert 'Batch mode only: validate the selected detected folders independently from the parent-folder discovery scan.' in normalized


def test_app_js_requires_batch_validation_before_generation() -> None:
    script = APP_JS.read_text()

    assert 'const batchScanButton = document.getElementById("batch-scan-button");' in script
    assert 'batchParentScanComplete: false,' in script
    assert 'batchValidationReady: false,' in script
    assert 'validatedBatchFolders: [],' in script
    assert 'function setBatchValidationResults(results = []) {' in script
    assert 'function hasValidatedBatchSelection() {' in script
    assert 'async function validateSelectedBatchFolders() {' in script
    assert 'await Promise.all(selectedBatchFolders.map(async (folderPath) => {' in script
    assert 'postJson("/api/jobs/scan-folder", { folder_path: folderPath })' in script
    assert 'badgeLabel: invalidResults.length === 0 ? "Validated" : "Needs attention"' in script
    assert 'batchScanButton?.addEventListener("click", async () => {' in script
    assert 'Run Scan selected folders successfully for the current batch selection before running batch page or cover-collage generation.' in script
    assert 'return hasValidatedBatchSelection();' in script


def test_app_js_resets_batch_validation_when_selection_changes() -> None:
    script = APP_JS.read_text()

    assert 'setBatchValidationResults([]);' in script
    assert 'setSelectedBatchFolders(nextSelection);' in script
    assert 'selectAllSubfoldersButton?.addEventListener("click", () => {' in script
    assert 'clearSubfolderSelectionButton?.addEventListener("click", () => {' in script


def test_app_js_renders_batch_cover_collage_results_per_folder() -> None:
    script = APP_JS.read_text()

    assert 'function renderBatchFolderOutcomeSection(results) {' in script
    assert 'function renderBatchCoverCollageSummary(result) {' in script
    assert 'if (Array.isArray(result.bundle_results)) {' in script
    assert '{ label: "Selected folders processed", value: pluralize(result.processed_folders ?? bundleResults.length, "folder") }' in script
    assert '{ label: "Folders successfully generated", value: pluralize(result.generated_folders ?? successfulResults.length, "folder") }' in script
    assert '{ label: "Total collage files written", value: pluralize(totalCollageFilesWritten, "file") }' in script
    assert '<h4>Per-folder outcomes</h4>' in script
    assert 'const status = result.success ? "Success" : "Failed";' in script
    assert 'renderGenerationSummary(batchResult);' in script


def test_app_js_routes_every_request_through_the_error_aware_helper() -> None:
    """A failed request used to render as "Finished — Done."."""
    script = APP_JS.read_text()

    assert script.count("fetch(") == 1
    assert "if (response.ok && data) {" in script
    assert "typeof data?.detail === \"string\"" in script
    assert script.count("renderFailedResult(generationResultEl, errorMessage);") == 3
    assert "await runExclusive(runPageGeneration);" in script
    assert "await runExclusive(runCoverCollage);" in script


def test_app_js_reads_and_resets_manual_cover_collage_include_list() -> None:
    script = APP_JS.read_text()

    assert 'const coverCollageIncludeListEl = document.getElementById("cover-collage-include-list");' in script
    assert 'function readSelectedCoverCollageImages() {' in script
    assert '.split(/[\\n,]+/u)' in script
    assert 'selected_cover_images: readSelectedCoverCollageImages(),' in script
    assert 'function resetCoverCollageIncludeList() {' in script
    assert 'resetCoverCollageIncludeList();' in script
