import re
from importlib.resources import files

# Read from the installed package, so these also prove the assets ship in it.
PACKAGE = files("pasteup")
INDEX_TEMPLATE = PACKAGE / "templates" / "index.html"
APP_JS = PACKAGE / "static" / "js" / "app.js"


def _squash_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def test_index_exposes_batch_validation_controls_and_copy() -> None:
    html = INDEX_TEMPLATE.read_text()
    normalized = _squash_whitespace(html)

    assert 'id="subfolder-picker-section"' in html
    assert 'id="batch-subfolder-checklist"' in html
    assert 'button id="select-all-subfolders-button"' in normalized
    assert 'button id="clear-subfolder-selection-button"' in normalized
    assert 'button id="batch-scan-button" class="primary-button" type="button">Check selected bundles</button>' in normalized
    assert 'id="cover-collage-include-list"' in html
    assert "Cover collage include list" in html
    assert "one per line or comma-separated" in html
    assert 'id="batch-selection-status" class="status-line" role="status" aria-live="polite">Pick bundles, then check them before making images.</p>' in normalized


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
    assert 'function renderBatchCheckSummary() {' in script
    assert 'batchScanButton?.addEventListener("click", async () => {' in script
    assert 'renderPendingResult(generationResultEl, "Check bundles", "Check the picked bundles before making images.");' in script
    assert 'renderPendingResult(generationResultEl, "Check bundles", "Check the picked bundles before making covers.");' in script
    assert 'return hasValidatedBatchSelection();' in script


def test_app_js_rechecks_batch_readiness_when_selection_changes() -> None:
    """Ready only while every picked bundle passed its last check."""
    script = APP_JS.read_text()

    assert 'setBatchValidationResults([]);' in script
    assert 'function refreshBatchValidationReadiness() {' in script
    assert '&& selectedPaths.every((folderPath) => validatedPathSet.has(folderPath));' in script
    assert 'setSelectedBatchFolders(nextSelection);\n      applyBatchSelectionChange();' in script
    assert 'selectAllSubfoldersButton?.addEventListener("click", () => {' in script
    assert 'clearSubfolderSelectionButton?.addEventListener("click", () => {' in script
    assert script.count("applyBatchSelectionChange();") == 3


def test_app_js_checks_every_listed_bundle_after_a_batch_scan() -> None:
    script = APP_JS.read_text()

    assert 'generationState.selectedBatchFolders = generationState.mode === "batch" && selectedBatchFolders.length === 0' in script
    assert 'if (generationState.mode === "batch" && hasSelectedBatchFolders()) {\n    await validateSelectedBatchFolders();' in script
    # Both ways of picking a folder, scanning a typed path and choosing one in
    # the folder browser, go on to check the bundles.
    assert script.count("await runExclusive(scanFolderAndCheckBundles);") == 2


def test_app_js_scans_the_folder_picked_inside_a_single_bundle_folder() -> None:
    """Picking a folder used to leave the buttons locked: nothing scanned it."""
    script = APP_JS.read_text()

    assert 'inputFolderEl.value = subfolderPickerEl.value;' in script
    assert 'await runExclusive(() => scanCurrentFolder());' in script


def test_index_offers_a_folder_browser_beside_the_folder_field() -> None:
    html = INDEX_TEMPLATE.read_text()
    normalized = _squash_whitespace(html)

    # Named after the field's label, so it reads "Browse… Bundle folder".
    assert 'aria-labelledby="browse-folder-button input-folder-label"' in html
    assert '<dialog id="folder-browser" class="folder-browser"' in html
    assert 'button id="folder-browser-choose" class="primary-button" type="button">Use this folder</button>' in normalized


def test_app_js_browses_through_the_api_and_scans_the_folder_chosen() -> None:
    script = APP_JS.read_text()

    assert 'postJson("/api/jobs/browse-folder", { folder_path: folderPath })' in script
    assert "folderBrowserEl.showModal();" in script
    # Only the latest listing is drawn, so a slow one can't replace a newer one.
    assert "if (requestId !== folderBrowserState.requestId) {\n    return;\n  }" in script
    assert "inputFolderEl.value = chosenPath;" in script
    # Disabled with the scan buttons while a job runs.
    assert "[scanButton, batchScanButton, browseFolderButton].forEach((button) => {" in script


def test_index_offers_upscaling_as_an_output_of_its_own() -> None:
    html = INDEX_TEMPLATE.read_text()
    normalized = _squash_whitespace(html)
    select = html[html.index('<select id="upscale-scale"') : html.index("</select>", html.index('<select id="upscale-scale"'))]

    assert [f'<option value="{scale}"' in select for scale in (2, 3, 4)] == [True, True, True]
    assert 'button id="upscale-button" class="secondary-button" type="button" disabled>Upscale images</button>' in normalized


def test_app_js_upscales_one_bundle_or_many() -> None:
    script = APP_JS.read_text()

    assert 'postJson("/api/jobs/upscale-images", readUpscalePayload())' in script
    assert 'postJson("/api/jobs/upscale-images-batch", payload)' in script
    assert script.count('renderGenerationSummary(result, "upscale");') == 1
    assert script.count('renderGenerationSummary(batchResult, "upscale");') == 1
    # Unlocked on the same terms as a cover, and locked while a job runs.
    assert "const upscaleReady = coverCollageReady;" in script
    assert "upscaleButton.disabled = !upscaleReady || generationState.busy;" in script


def test_app_js_renders_batch_cover_collage_results_per_folder() -> None:
    script = APP_JS.read_text()

    assert 'function renderBatchFolderOutcomeSection(results, kind, scale) {' in script
    assert 'function renderBatchSummary(result, kind) {' in script
    assert 'if (Array.isArray(result.bundle_results)) {' in script
    assert '{ label: "Bundles done", value: `${doneCount} of ${totalCount}` },' in script
    assert 'renderListSection("Each bundle", lines, "", { limit: Infinity });' in script
    assert 'renderGenerationSummary(batchResult, "cover");' in script
    assert 'renderGenerationSummary(result, "sheets");' in script


def test_app_js_counts_batch_sheets_from_pages_not_files() -> None:
    """Batch sheet results carry no file list, so "files written" used to read 0."""
    script = APP_JS.read_text()

    assert '{ label: "Sheets", value: pluralize(sum("pages_generated"), "sheet") },' in script
    assert 'bundleResult?.success && (isCover || (bundleResult.pages_generated ?? 0) > 0)' in script


def test_app_js_reads_result_details_from_fields_not_prose() -> None:
    script = APP_JS.read_text()

    assert 'describeLeftOutImages(result.images_dropped ?? 0),' in script
    assert 'result.images_skipped > 0' in script
    assert 'result.backgrounds_cleaned > 0' in script


def test_app_js_routes_every_request_through_the_error_aware_helper() -> None:
    """A failed request used to render as "Finished — Done."."""
    script = APP_JS.read_text()

    assert script.count("fetch(") == 1
    assert "if (response.ok && data) {" in script
    assert "typeof data?.detail === \"string\"" in script
    # Sheets, one cover, covers for many bundles, and upscaling one or many.
    assert script.count("renderFailedResult(generationResultEl, errorMessage);") == 5
    assert "await runExclusive(runPageGeneration);" in script
    assert "await runExclusive(runCoverCollage);" in script
    assert "await runExclusive(runUpscale);" in script


def test_app_js_reads_and_resets_manual_cover_collage_include_list() -> None:
    script = APP_JS.read_text()

    assert 'const coverCollageIncludeListEl = document.getElementById("cover-collage-include-list");' in script
    assert 'function readSelectedCoverCollageImages() {' in script
    assert '.split(/[\\n,]+/u)' in script
    assert 'selected_cover_images: readSelectedCoverCollageImages(),' in script
    assert 'function resetCoverCollageIncludeList() {' in script
    assert 'resetCoverCollageIncludeList();' in script
