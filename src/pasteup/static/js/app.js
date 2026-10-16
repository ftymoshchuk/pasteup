// Matches IMAGES_PER_PAGE in services/image_batcher.py: a sheet is a 4 x 3 grid.
const IMAGES_PER_SHEET = 12;
const PART_FILLED_OPTION = "“Include a part-filled last page”";
const GENERATION_MODES = {
  single: {
    inputLabel: "Bundle folder",
    outputLabel: "Saves to",
    endpoint: "/api/jobs/generate",
    payload: () => ({
      folder_path: readWorkingFolderPath(),
      output_path: outputFolderEl.value.trim(),
      ...readCommonGenerationSettings(),
    }),
    statusMessage: "Making preview sheets…",
    buttonText: "Make preview sheets",
    helpText: "Point Pasteup at the folder that holds one bundle's images.",
    modeStepCopy: "Counts your images and checks they can be read.",
    folderStepCopy: "Results go in a ---Created--- folder next to it.",
    outputStepCopy: "Preview sheets of every image, or one cover for the listing.",
    outputHintReady: "Ready! Make preview sheets, a cover, or both.",
  },
  batch: {
    inputLabel: "Folder of bundles",
    outputLabel: "Saves to",
    endpoint: "/api/jobs/generate-all-folders",
    payload: () => readBatchFolderPayload(),
    statusMessage: "Making preview sheets for the selected bundles…",
    buttonText: "Make preview sheets",
    helpText: "Point Pasteup at a folder with one folder inside per bundle.",
    modeStepCopy: "Lists the bundle folders inside and checks each one.",
    folderStepCopy: "Each bundle gets its own folder inside a ---Created--- folder next to it.",
    outputStepCopy: "Preview sheets or a cover for every bundle you checked.",
    outputHintReady: "Ready! Make images for the checked bundles.",
  },
};

const generationModeEls = document.querySelectorAll('input[name="generation-mode"]');
const inputFolderLabelEl = document.getElementById("input-folder-label");
const outputFolderLabelEl = document.getElementById("output-folder-label");
const modeHelpEl = document.getElementById("mode-help");
const modeStepCopyEl = document.getElementById("mode-step-copy");
const folderStepCopyEl = document.getElementById("folder-step-copy");
const outputStepCopyEl = document.getElementById("output-step-copy");
const inputFolderEl = document.getElementById("input-folder");
const outputFolderEl = document.getElementById("output-folder");
const pageWidthEl = document.getElementById("page-width");
const pageHeightEl = document.getElementById("page-height");
const gapEl = document.getElementById("gap");
const marginEl = document.getElementById("margin");
const formatEl = document.getElementById("format");
const createPreviewVideoEl = document.getElementById("create-preview-video");
const videoDurationSecondsEl = document.getElementById("video-duration-seconds");
const videoTransitionEl = document.getElementById("video-transition");
const createPreviewVideoHelpEl = document.getElementById("create-preview-video-help");
const coverCollageTemplateEl = document.getElementById("cover-collage-template");
const coverCollageIncludeListEl = document.getElementById("cover-collage-include-list");
const pageUnitEl = document.getElementById("page-unit");
const dpiEl = document.getElementById("dpi");
const backgroundCleanModeEl = document.getElementById("background-clean-mode");
const backgroundToleranceEl = document.getElementById("background-tolerance");
const backgroundFeatherEl = document.getElementById("background-feather");
const includePartialPageEl = document.getElementById("include-partial-page");

const scanButton = document.getElementById("scan-button");
const generateButton = document.getElementById("generate-button");
const coverCollageButton = document.getElementById("cover-collage-button");
const outputActionsSectionEl = document.getElementById("output-actions-section");
const outputActionsHintEl = document.getElementById("output-actions-hint");
const scanResultEl = document.getElementById("scan-result");
const generationResultEl = document.getElementById("generation-result");
const subfolderSectionEl = document.getElementById("subfolder-picker-section");
const subfolderSingleControlsEl = document.getElementById("subfolder-single-controls");
const subfolderBatchControlsEl = document.getElementById("subfolder-batch-controls");
const subfolderPickerEl = document.getElementById("subfolder-picker");
const batchSubfolderChecklistEl = document.getElementById("batch-subfolder-checklist");
const useSubfolderButton = document.getElementById("use-subfolder-button");
const selectAllSubfoldersButton = document.getElementById("select-all-subfolders-button");
const clearSubfolderSelectionButton = document.getElementById("clear-subfolder-selection-button");
const batchScanButton = document.getElementById("batch-scan-button");
const batchSelectionSummaryEl = document.getElementById("batch-selection-summary");
const batchSelectionStatusEl = document.getElementById("batch-selection-status");
const videoSettingsEl = document.getElementById("video-settings");
const backgroundCleanSettingsEl = document.getElementById("background-clean-settings");
const browseFolderButton = document.getElementById("browse-folder-button");
const folderBrowserEl = document.getElementById("folder-browser");
const folderBrowserTitleEl = document.getElementById("folder-browser-title");
const folderBrowserPlacesEl = document.getElementById("folder-browser-places");
const folderBrowserCrumbsEl = document.getElementById("folder-browser-crumbs");
const folderBrowserNoticeEl = document.getElementById("folder-browser-notice");
const folderBrowserListEl = document.getElementById("folder-browser-list");
const folderBrowserStatusEl = document.getElementById("folder-browser-status");
const folderBrowserCancelButton = document.getElementById("folder-browser-cancel");
const folderBrowserChooseButton = document.getElementById("folder-browser-choose");

const generationState = {
  mode: document.querySelector('input[name="generation-mode"]:checked')?.value || "single",
  singleFolderReady: false,
  scannedRootFolder: "",
  outputDerivationSourceFolder: "",
  selectedWorkingFolder: "",
  availableSubfolders: [],
  selectedBatchFolders: [],
  batchParentScanComplete: false,
  batchValidationReady: false,
  validatedBatchFolders: [],
  batchValidationResults: [],
  validatedBatchSelectionSignature: "",
  busy: false,
};

// Every action posts JSON and renders the reply. Failures arrive in three
// shapes: a `message` from a failed generation, FastAPI's `detail` (a string, or
// a list of validation errors), or no JSON at all when the request never
// completed. They are normalised here so no caller renders an error as success.
async function postJson(url, payload) {
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    return { ok: false, data: null, errorMessage: `Can't reach Pasteup. Is it still running? (${error.message})` };
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (response.ok && data) {
    return { ok: true, data, errorMessage: "" };
  }

  return { ok: false, data, errorMessage: describeErrorResponse(response, data) };
}

function describeErrorResponse(response, data) {
  if (typeof data?.message === "string" && data.message) {
    return data.message;
  }

  if (typeof data?.detail === "string" && data.detail) {
    return data.detail;
  }

  if (Array.isArray(data?.detail) && data.detail.length > 0) {
    return data.detail
      .map((issue) => {
        const field = Array.isArray(issue?.loc) ? issue.loc.filter((part) => part !== "body").join(".") : "";
        return field ? `${field}: ${issue?.msg}` : String(issue?.msg ?? "");
      })
      .join(" ");
  }

  return `The server returned an error (HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ""}).`;
}

// One request-backed action at a time: while it runs, the action buttons are
// disabled, so a second click cannot start a duplicate export.
async function runExclusive(action) {
  if (generationState.busy) {
    return;
  }

  setBusy(true);
  try {
    await action();
  } finally {
    setBusy(false);
  }
}

function setBusy(isBusy) {
  generationState.busy = Boolean(isBusy);
  document.body.classList.toggle("is-busy", generationState.busy);
  recomputeStepFiveState();
}

// Each result card sits beside its step on wide screens and below it on narrow
// ones, where it can be out of view; bring the one about to change into view.
function revealResult(container) {
  const panel = container.closest(".result-panel") || container;
  const { top } = panel.getBoundingClientRect();
  if (top < 0 || top > window.innerHeight * 0.75) {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    panel.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  }
}

function fileName(path) {
  return String(path).split(/[\\/]/).pop() || String(path);
}

// Print resolution and background cleaning. Kept separate from the video
// settings so the cover-collage payloads, which enumerate their fields rather
// than spreading everything, can pick these up without also sending video keys
// their endpoint does not accept.
function readOutputQualitySettings() {
  const backgroundCleanMode = backgroundCleanModeEl?.value || "off";
  return {
    page_unit: pageUnitEl?.value || "px",
    dpi: Number(dpiEl?.value) || 300,
    background_clean_mode: backgroundCleanMode,
    // Hidden while cleaning is off, so only sent when it is on: a value left
    // out of range in a hidden field must not fail the request.
    ...(backgroundCleanMode === "off" ? {} : {
      background_tolerance: Number(backgroundToleranceEl?.value ?? 240),
      background_feather: Number(backgroundFeatherEl?.value ?? 1),
    }),
  };
}

function readCommonGenerationSettings() {
  return {
    ...readOutputQualitySettings(),
    include_partial_page: Boolean(includePartialPageEl?.checked),
    page_width: Number(pageWidthEl.value),
    page_height: Number(pageHeightEl.value),
    gap: Number(gapEl.value),
    margin: Number(marginEl.value),
    format: formatEl.value,
    create_preview_video: Boolean(createPreviewVideoEl?.checked),
    // Likewise hidden while no video is wanted.
    duration_seconds: createPreviewVideoEl?.checked ? Number(videoDurationSecondsEl?.value) : undefined,
    transition: videoTransitionEl?.value || "none",
  };
}

// Point at the field to fix: open the section it is in, then let the browser
// focus it and show its own range message beside it.
function reportSettingsProblem(message, field) {
  renderResultCard(generationResultEl, { tone: "warning", badgeLabel: "Check settings", message });
  const disclosure = field?.closest("details");
  if (disclosure) {
    disclosure.open = true;
  }
  if (field?.reportValidity()) {
    field.focus();
  }
}

function validateVideoGenerationSettings() {
  if (!createPreviewVideoEl?.checked) {
    return true;
  }

  const commonSettings = readCommonGenerationSettings();
  const maxDurationSeconds = Number(videoDurationSecondsEl?.max) || 120;

  if (!(commonSettings.duration_seconds > 0) || commonSettings.duration_seconds > maxDurationSeconds) {
    reportSettingsProblem(`The video must be 1 to ${maxDurationSeconds} seconds long.`, videoDurationSecondsEl);
    return false;
  }

  return true;
}

function validateOutputQualitySettings() {
  const quality = readOutputQualitySettings();

  if (!Number.isFinite(quality.dpi) || quality.dpi <= 0 || quality.dpi > 1200) {
    reportSettingsProblem("DPI must be between 1 and 1200.", dpiEl);
    return false;
  }

  if (quality.background_clean_mode === "off") {
    return true;
  }

  if (!(quality.background_tolerance >= 0 && quality.background_tolerance <= 255)) {
    reportSettingsProblem("Tolerance must be between 0 and 255.", backgroundToleranceEl);
    return false;
  }

  if (!(quality.background_feather >= 0 && quality.background_feather <= 25)) {
    reportSettingsProblem("Edge softening must be between 0 and 25.", backgroundFeatherEl);
    return false;
  }

  return true;
}

function readMainInputFolderPath() {
  return inputFolderEl.value.trim();
}

function readWorkingFolderPath() {
  return generationState.selectedWorkingFolder || readMainInputFolderPath();
}

function clearSelectedWorkingFolder() {
  generationState.selectedWorkingFolder = "";
}

function normalizeSelectedBatchFolders(selectedPaths = generationState.selectedBatchFolders, availableSubfolders = generationState.availableSubfolders) {
  const availablePathSet = new Set((Array.isArray(availableSubfolders) ? availableSubfolders : []).map(({ fullPath }) => fullPath));
  const seenPaths = new Set();

  return (Array.isArray(selectedPaths) ? selectedPaths : [])
    .map((path) => (typeof path === "string" ? path.trim() : ""))
    .filter((path) => path && availablePathSet.has(path) && !seenPaths.has(path) && seenPaths.add(path));
}

function setSelectedBatchFolders(selectedPaths = []) {
  generationState.selectedBatchFolders = normalizeSelectedBatchFolders(selectedPaths);
}

function resetBatchValidationState() {
  generationState.batchParentScanComplete = false;
  generationState.batchValidationReady = false;
  generationState.validatedBatchFolders = [];
  generationState.batchValidationResults = [];
  generationState.validatedBatchSelectionSignature = "";
}

function hasSelectedBatchFolders() {
  return getSelectedBatchFolderPaths().length > 0;
}

function setBatchParentScanComplete(isComplete) {
  generationState.batchParentScanComplete = Boolean(isComplete);
  if (!generationState.batchParentScanComplete) {
    generationState.batchValidationReady = false;
    generationState.validatedBatchSelectionSignature = "";
  }
}

function getBatchSelectionSignature(selectedPaths = getSelectedBatchFolderPaths()) {
  return [...selectedPaths].sort().join("||");
}

function setBatchValidationResults(results = []) {
  generationState.batchValidationResults = Array.isArray(results) ? results : [];
  generationState.validatedBatchFolders = generationState.batchValidationResults
    .filter((result) => result?.valid && typeof result.folderPath === "string")
    .map((result) => result.folderPath);
  refreshBatchValidationReadiness();
}

// A selection is ready when every picked bundle passed its last check, so
// unticking a bundle (say, one that failed) needs no new check; picking one
// that was never checked, or that failed, does.
function refreshBatchValidationReadiness() {
  const selectedPaths = getSelectedBatchFolderPaths();
  const validatedPathSet = new Set(generationState.validatedBatchFolders);
  generationState.batchValidationReady = selectedPaths.length > 0
    && selectedPaths.every((folderPath) => validatedPathSet.has(folderPath));
  generationState.validatedBatchSelectionSignature = generationState.batchValidationReady
    ? getBatchSelectionSignature(selectedPaths)
    : "";
}

// After the picks change, readiness and the check card follow the new picks.
function applyBatchSelectionChange() {
  refreshBatchValidationReadiness();
  if (generationState.batchValidationResults.length > 0) {
    renderBatchCheckSummary();
  }
}

function countFailedSelectedBatchFolders() {
  const selectedPathSet = new Set(getSelectedBatchFolderPaths());
  return generationState.batchValidationResults
    .filter((result) => !result?.valid && selectedPathSet.has(result?.folderPath))
    .length;
}

function hasValidatedBatchSelection() {
  if (generationState.mode !== "batch") {
    return true;
  }

  const selectedPaths = getSelectedBatchFolderPaths();
  if (selectedPaths.length === 0) {
    return false;
  }

  const validatedPathSet = new Set(generationState.validatedBatchFolders);
  return generationState.batchValidationReady
    && generationState.validatedBatchSelectionSignature === getBatchSelectionSignature(selectedPaths)
    && selectedPaths.every((folderPath) => validatedPathSet.has(folderPath));
}


function setAvailableSubfolders(subfolders) {
  generationState.availableSubfolders = Array.isArray(subfolders)
    ? subfolders.map(normalizeSubfolderOption).filter(Boolean)
    : [];
  setSelectedBatchFolders(generationState.selectedBatchFolders);
}

function setScannedRootFolder(folderPath) {
  generationState.scannedRootFolder = typeof folderPath === "string" ? folderPath.trim() : "";
}

function setOutputDerivationSourceFolder(folderPath) {
  generationState.outputDerivationSourceFolder = typeof folderPath === "string" ? folderPath.trim() : "";
}

function readSingleFolderPayload() {
  return {
    folder_path: readWorkingFolderPath(),
    output_path: outputFolderEl.value.trim(),
    ...readCommonGenerationSettings(),
  };
}

function readBatchFolderPayload() {
  const selectedSubfolderPaths = getSelectedBatchFolderPaths();

  return {
    parent_folder_path: inputFolderEl.value.trim(),
    created_output_root_path: outputFolderEl.value.trim(),
    selected_subfolders: selectedSubfolderPaths,
    ...readCommonGenerationSettings(),
  };
}

function readSelectedCoverCollageTemplate() {
  return coverCollageTemplateEl?.value || "randomized-grid";
}

function readSelectedCoverCollageTemplateLabel() {
  return coverCollageTemplateEl?.selectedOptions?.[0]?.textContent?.trim() || "selected template";
}

function readSelectedCoverCollageImages() {
  const rawValue = coverCollageIncludeListEl?.value || "";
  const normalizedItems = rawValue
    .split(/[\n,]+/u)
    .map((value) => value.trim())
    .filter(Boolean);

  return normalizedItems.length > 0
    ? [...new Set(normalizedItems)]
    : null;
}

function readCoverCollagePayload(folderPath = readWorkingFolderPath(), outputPath = outputFolderEl.value.trim()) {
  const commonSettings = readCommonGenerationSettings();
  return {
    folder_path: folderPath,
    output_path: outputPath,
    page_width: commonSettings.page_width,
    page_height: commonSettings.page_height,
    format: commonSettings.format,
    collage_template: readSelectedCoverCollageTemplate(),
    selected_cover_images: readSelectedCoverCollageImages(),
    ...readOutputQualitySettings(),
  };
}

function buildBatchCoverCollagePayload() {
  const commonSettings = readCommonGenerationSettings();
  return {
    parent_folder_path: inputFolderEl.value.trim(),
    created_output_root_path: outputFolderEl.value.trim(),
    selected_subfolders: getSelectedBatchFolderPaths(),
    page_width: commonSettings.page_width,
    page_height: commonSettings.page_height,
    format: commonSettings.format,
    collage_template: readSelectedCoverCollageTemplate(),
    ...readOutputQualitySettings(),
  };
}


function splitFolderPath(folderPath) {
  if (typeof folderPath !== "string") {
    return null;
  }

  const trimmedPath = folderPath.trim();
  if (!trimmedPath) {
    return null;
  }

  const normalizedPath = trimmedPath.replace(/[\\/]+$/, "");
  if (!normalizedPath) {
    return null;
  }

  const lastSeparatorIndex = Math.max(normalizedPath.lastIndexOf("/"), normalizedPath.lastIndexOf("\\"));
  const baseName = normalizedPath.slice(lastSeparatorIndex + 1);

  if (!baseName || baseName === "." || baseName === "..") {
    return null;
  }

  const parentDirectory = lastSeparatorIndex >= 0 ? normalizedPath.slice(0, lastSeparatorIndex) : "";
  return { parentDirectory, baseName };
}

function buildDerivedOutputPath(folderPath) {
  const pathParts = splitFolderPath(folderPath);
  if (!pathParts) {
    return "";
  }

  const { parentDirectory, baseName } = pathParts;
  const includeBaseName = generationState.mode !== "batch";
  const derivedFolderName = includeBaseName ? `---Created---/${baseName}` : "---Created---";

  if (!parentDirectory) {
    return derivedFolderName;
  }

  const separator = parentDirectory.includes("\\") && !parentDirectory.includes("/") ? "\\" : "/";
  return `${parentDirectory}${separator}${derivedFolderName.replaceAll("/", separator)}`;
}

function syncDerivedOutputPath() {
  const sourceFolderPath = generationState.outputDerivationSourceFolder || (
    generationState.mode === "single"
      ? generationState.scannedRootFolder || readMainInputFolderPath()
      : readMainInputFolderPath()
  );
  outputFolderEl.value = buildDerivedOutputPath(sourceFolderPath);
}

function resetCoverCollageIncludeList() {
  if (coverCollageIncludeListEl) {
    coverCollageIncludeListEl.value = "";
  }
}

function getSelectedGenerationModeConfig() {
  return GENERATION_MODES[generationState.mode] || GENERATION_MODES.single;
}

function getSelectedBatchFolderPaths() {
  return normalizeSelectedBatchFolders(generationState.selectedBatchFolders);
}

function getBatchGenerationSelectionDetails() {
  const availableCount = generationState.availableSubfolders.length;
  const selectedBatchFolders = getSelectedBatchFolderPaths();
  const selectedCount = selectedBatchFolders.length;
  const isAllSelected = availableCount > 0 && selectedCount === availableCount;

  return {
    availableCount,
    selectedCount,
    isAllSelected,
    selectedBatchFolders,
  };
}

function recomputeStepFiveState() {
  syncBatchWorkingFolderSelection();
  updateBatchSelectionSummary();
  updateOutputActionState();
}

function getBatchSelectionValidationMessage() {
  if (generationState.mode !== "batch") {
    return "";
  }

  const { availableCount, selectedCount, isAllSelected, selectedBatchFolders } = getBatchGenerationSelectionDetails();
  if (!generationState.batchParentScanComplete) {
    return "Scan the folder of bundles to list them.";
  }

  if (availableCount === 0) {
    return "No bundle folders were found inside it.";
  }

  if (selectedCount === 0) {
    return `Pick at least one of the ${pluralize(availableCount, "bundle")}.`;
  }

  if (!hasValidatedBatchSelection()) {
    const failedCount = countFailedSelectedBatchFolders();
    if (failedCount > 0) {
      return failedCount === 1
        ? "1 picked bundle needs attention. Untick it, or fix it and check again."
        : `${failedCount} picked bundles need attention. Untick them, or fix them and check again.`;
    }

    return `${pluralize(selectedCount, "bundle")} picked. Check ${selectedCount === 1 ? "it" : "them"} before making images.`;
  }

  const validatedSelectedCount = selectedCount;

  if (isAllSelected && availableCount > 1) {
    return `All ${availableCount} bundles are checked and ready.`;
  }

  return `${pluralize(validatedSelectedCount, "bundle")} checked and ready.`;
}

function updateBatchSelectionStatus() {
  if (!batchSelectionStatusEl) {
    return;
  }

  const message = getBatchSelectionValidationMessage();
  batchSelectionStatusEl.textContent = message || "";
  batchSelectionStatusEl.classList.toggle("status-error", generationState.mode === "batch" && generationState.batchParentScanComplete && getBatchGenerationSelectionDetails().selectedCount === 0);
}

function isSingleGenerationReady() {
  return generationState.singleFolderReady;
}

function isBatchGenerationReady() {
  if (generationState.mode !== "batch") {
    return isSingleGenerationReady();
  }

  if (!generationState.batchParentScanComplete || !hasSelectedBatchFolders() || !generationState.batchValidationReady) {
    return false;
  }

  return hasValidatedBatchSelection();
}

function syncBatchWorkingFolderSelection() {
  if (generationState.mode !== "batch") {
    return;
  }

  const { selectedBatchFolders: selectedBatchPaths } = getBatchGenerationSelectionDetails();
  generationState.selectedWorkingFolder = selectedBatchPaths.length === 1 ? selectedBatchPaths[0] : "";
}

function isCoverCollageReady() {
  if (generationState.mode !== "batch") {
    return generationState.singleFolderReady;
  }

  if (!generationState.batchParentScanComplete || !generationState.batchValidationReady || !hasValidatedBatchSelection()) {
    return false;
  }

  const { selectedCount } = getBatchGenerationSelectionDetails();

  return selectedCount > 0;
}

function getGenerationButtonLabel() {
  const previewVideoEnabled = Boolean(createPreviewVideoEl?.checked);

  if (generationState.mode !== "batch") {
    return previewVideoEnabled ? "Make sheets + video" : getSelectedGenerationModeConfig().buttonText;
  }

  const { selectedCount } = getBatchGenerationSelectionDetails();

  if (selectedCount === 0) {
    return previewVideoEnabled ? "Make sheets + videos" : "Make preview sheets";
  }

  return previewVideoEnabled
    ? `Make sheets + videos for ${pluralize(selectedCount, "bundle")}`
    : `Make sheets for ${pluralize(selectedCount, "bundle")}`;
}

function updatePreviewVideoControls() {
  const previewVideoEnabled = Boolean(createPreviewVideoEl?.checked);

  if (videoSettingsEl) {
    videoSettingsEl.hidden = !previewVideoEnabled;
  }

  if (videoDurationSecondsEl) {
    videoDurationSecondsEl.disabled = !previewVideoEnabled;
  }

  if (videoTransitionEl) {
    videoTransitionEl.disabled = !previewVideoEnabled;
  }

  if (createPreviewVideoHelpEl) {
    createPreviewVideoHelpEl.textContent = previewVideoEnabled
      ? "Made with the sheets. Etsy takes videos of 5 to 15 seconds."
      : "An MP4 slideshow of the sheets, made at the same time.";
  }
}

// Tolerance and edge softening only mean something once cleaning is on.
function updateBackgroundCleanControls() {
  if (backgroundCleanSettingsEl) {
    backgroundCleanSettingsEl.hidden = (backgroundCleanModeEl?.value || "off") === "off";
  }
}

function getCoverCollageButtonLabel() {
  if (generationState.mode !== "batch") {
    return "Make cover";
  }

  const { selectedCount } = getBatchGenerationSelectionDetails();

  if (selectedCount === 0) {
    return "Make covers";
  }

  return selectedCount === 1 ? "Make cover for 1 bundle" : `Make covers for ${selectedCount} bundles`;
}

function getGenerationStatusMessage() {
  if (generationState.mode !== "batch") {
    return getSelectedGenerationModeConfig().statusMessage;
  }

  const { availableCount, selectedCount } = getBatchGenerationSelectionDetails();
  if (availableCount === 0 || selectedCount === 0) {
    return getSelectedGenerationModeConfig().statusMessage;
  }

  return `Making preview sheets for ${pluralize(selectedCount, "bundle")}…`;
}

function getOutputActionsHint() {
  if (generationState.mode !== "batch") {
    if (!generationState.singleFolderReady) {
      return "Scan a folder first. These unlock once it has images.";
    }
    return getSelectedGenerationModeConfig().outputHintReady;
  }

  const { availableCount, selectedCount, isAllSelected } = getBatchGenerationSelectionDetails();
  if (!generationState.batchParentScanComplete) {
    return "Scan the folder of bundles first.";
  }

  if (availableCount === 0) {
    return "No bundle folders were found to make images for.";
  }

  if (selectedCount === 0) {
    return "Pick bundles in step 1, then check them.";
  }

  if (!hasValidatedBatchSelection()) {
    return countFailedSelectedBatchFolders() > 0
      ? "Some picked bundles need attention. See step 1."
      : `Check the ${pluralize(selectedCount, "picked bundle")} in step 1 first.`;
  }

  if (isAllSelected && availableCount > 1) {
    return `Ready! Make images for all ${availableCount} bundles.`;
  }

  return `Ready! Make images for ${pluralize(selectedCount, "bundle")}.`;
}

function updateOutputActionState() {
  const isBatchMode = generationState.mode === "batch";
  const generationReady = isBatchMode ? isBatchGenerationReady() : isSingleGenerationReady();
  const batchCoverCollageReady = generationState.batchParentScanComplete
    && hasSelectedBatchFolders()
    && hasValidatedBatchSelection();
  const coverCollageReady = isBatchMode ? batchCoverCollageReady : isCoverCollageReady();
  const outputActionsEnabled = isBatchMode
    ? generationReady || coverCollageReady
    : generationState.singleFolderReady;

  generateButton.textContent = getGenerationButtonLabel();
  coverCollageButton.textContent = getCoverCollageButtonLabel();
  generateButton.disabled = !generationReady || generationState.busy;
  coverCollageButton.disabled = !coverCollageReady || generationState.busy;
  [scanButton, batchScanButton, browseFolderButton].forEach((button) => {
    if (button) {
      button.disabled = generationState.busy;
    }
  });
  generateButton.classList.toggle("primary-button", generationReady);
  generateButton.classList.toggle("secondary-button", !generationReady);
  coverCollageButton.classList.toggle("primary-button", coverCollageReady);
  coverCollageButton.classList.toggle("secondary-button", !coverCollageReady);
  outputActionsSectionEl.classList.toggle("workflow-step--disabled", !outputActionsEnabled);
  outputActionsHintEl.textContent = getOutputActionsHint();
  updateBatchSelectionStatus();
}

function updateBatchSelectionSummary() {
  if (!batchSelectionSummaryEl) {
    return;
  }

  const { selectedCount } = getBatchGenerationSelectionDetails();
  const availableCount = generationState.availableSubfolders.length;
  const selectedLabels = generationState.availableSubfolders
    .filter(({ fullPath }) => generationState.selectedBatchFolders.includes(fullPath))
    .map(({ displayName }) => displayName);

  if (!generationState.batchParentScanComplete) {
    batchSelectionSummaryEl.textContent = "Scan the folder of bundles to list them.";
    updateBatchSelectionStatus();
    return;
  }

  if (availableCount === 0) {
    batchSelectionSummaryEl.textContent = "No bundle folders found yet.";
    updateBatchSelectionStatus();
    return;
  }

  if (selectedCount === 0) {
    batchSelectionSummaryEl.textContent = `0 of ${pluralize(availableCount, "bundle")} picked.`;
    updateBatchSelectionStatus();
    return;
  }

  const summarySuffix = selectedLabels.length > 0
    ? `: ${selectedLabels.join(", ")}`
    : "";
  batchSelectionSummaryEl.textContent = `${selectedCount} of ${pluralize(availableCount, "bundle")} picked${summarySuffix}.`;
  updateBatchSelectionStatus();
}

function renderBatchSubfolderChecklist() {
  if (!batchSubfolderChecklistEl) {
    return;
  }

  batchSubfolderChecklistEl.innerHTML = "";

  if (generationState.availableSubfolders.length === 0) {
    const emptyState = document.createElement("p");
    emptyState.className = "muted-text";
    emptyState.textContent = "Scan a folder of bundles to list them here.";
    batchSubfolderChecklistEl.append(emptyState);
    return;
  }

  const selectedPaths = new Set(generationState.selectedBatchFolders);
  generationState.availableSubfolders.forEach(({ displayName, fullPath }) => {
    const label = document.createElement("label");
    label.className = "subfolder-checklist__item";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = fullPath;
    checkbox.checked = selectedPaths.has(fullPath);
    checkbox.addEventListener("change", () => {
      const nextSelection = generationState.availableSubfolders
        .filter(({ fullPath: availablePath }) => {
          if (availablePath === fullPath) {
            return checkbox.checked;
          }

          return batchSubfolderChecklistEl.querySelector(`input[value="${CSS.escape(availablePath)}"]`)?.checked;
        })
        .map(({ fullPath: availablePath }) => availablePath);
      setSelectedBatchFolders(nextSelection);
      applyBatchSelectionChange();
      renderBatchSubfolderChecklist();
      recomputeStepFiveState();
    });

    const textNode = document.createElement("span");
    textNode.textContent = displayName;

    label.append(checkbox, textNode);
    batchSubfolderChecklistEl.append(label);
  });
}

function syncBatchSelectionUI() {
  renderBatchSubfolderChecklist();
  recomputeStepFiveState();
}

function updateSubfolderControlVisibility() {
  const isBatchMode = generationState.mode === "batch";
  subfolderSingleControlsEl?.classList.toggle("hidden", isBatchMode);
  subfolderSingleControlsEl?.toggleAttribute("hidden", isBatchMode);
  subfolderBatchControlsEl?.classList.toggle("hidden", !isBatchMode);
  subfolderBatchControlsEl?.toggleAttribute("hidden", !isBatchMode);
}

function applyGenerationMode() {
  const config = getSelectedGenerationModeConfig();
  const outputFolderIsReadOnly = true;

  inputFolderLabelEl.textContent = config.inputLabel;
  outputFolderLabelEl.textContent = config.outputLabel;
  modeHelpEl.textContent = config.helpText;
  modeStepCopyEl.textContent = config.modeStepCopy;
  folderStepCopyEl.textContent = config.folderStepCopy;
  outputStepCopyEl.textContent = config.outputStepCopy;
  generateButton.textContent = getGenerationButtonLabel();
  outputFolderEl.readOnly = outputFolderIsReadOnly;
  outputFolderEl.setAttribute("aria-readonly", String(outputFolderIsReadOnly));
  updateSubfolderControlVisibility();
  updatePreviewVideoControls();
  recomputeStepFiveState();
}

function resetScanReadyState() {
  generationState.singleFolderReady = false;
  if (generationState.mode === "batch") {
    resetBatchValidationState();
  }
  recomputeStepFiveState();
}

function resetSingleFolderSelectionState() {
  setScannedRootFolder("");
  setOutputDerivationSourceFolder("");
  clearSelectedWorkingFolder();
  setAvailableSubfolders([]);
  setSelectedBatchFolders([]);
  resetBatchValidationState();
  hideSubfolderPicker();
}

function setScanReadyState(isReady) {
  generationState.singleFolderReady = Boolean(isReady);
  if (generationState.mode === "batch") {
    setBatchParentScanComplete(true);
  }
  recomputeStepFiveState();
}

function hideSubfolderPicker({ preserveOptions = false } = {}) {
  subfolderSectionEl.hidden = true;
  subfolderSectionEl.classList.add("hidden");

  if (!preserveOptions) {
    subfolderPickerEl.innerHTML = "";
    batchSubfolderChecklistEl.innerHTML = "";
  }

  updateBatchSelectionSummary();
}

function normalizeSubfolderOption(subfolder) {
  if (subfolder && typeof subfolder === "object") {
    const fullPath = typeof subfolder.full_path === "string" ? subfolder.full_path : "";
    const displayName = typeof subfolder.display_name === "string" && subfolder.display_name.trim()
      ? subfolder.display_name.trim()
      : fullPath;

    if (fullPath) {
      return { displayName, fullPath };
    }
  }

  if (typeof subfolder === "string" && subfolder) {
    return { displayName: subfolder, fullPath: subfolder };
  }

  return null;
}

function showSubfolderPicker(availableSubfolders = generationState.availableSubfolders, selectedSubfolder = "") {
  const normalizedSubfolders = Array.isArray(availableSubfolders)
    ? availableSubfolders.map(normalizeSubfolderOption).filter(Boolean)
    : [];
  const preferredSelection = typeof selectedSubfolder === "string" ? selectedSubfolder : "";
  const preservedBatchSelection = normalizeSelectedBatchFolders(
    generationState.selectedBatchFolders,
    normalizedSubfolders,
  );

  generationState.availableSubfolders = normalizedSubfolders;
  generationState.selectedBatchFolders = preservedBatchSelection;
  subfolderPickerEl.innerHTML = "";
  batchSubfolderChecklistEl.innerHTML = "";

  normalizedSubfolders.forEach(({ displayName, fullPath }) => {
    const singleOption = document.createElement("option");
    singleOption.value = fullPath;
    singleOption.textContent = displayName;
    singleOption.selected = preferredSelection ? fullPath === preferredSelection : false;
    subfolderPickerEl.append(singleOption);

  });

  if (preferredSelection && normalizedSubfolders.some(({ fullPath }) => fullPath === preferredSelection)) {
    subfolderPickerEl.value = preferredSelection;
  }

  if (!preferredSelection && normalizedSubfolders.length > 0) {
    subfolderPickerEl.value = normalizedSubfolders[0].fullPath;
  }

  syncBatchSelectionUI();
  updateSubfolderControlVisibility();
  subfolderSectionEl.hidden = false;
  subfolderSectionEl.classList.remove("hidden");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function pluralize(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

// Long lists (every file of a big bundle) end in "and N more" rather than
// stretching the card far past the screen.
function renderListSection(title, items, emptyMessage = "", { limit = 8 } = {}) {
  if (!Array.isArray(items) || items.length === 0) {
    return emptyMessage
      ? `<section class="result-section"><h3>${escapeHtml(title)}</h3><p class="result-empty">${escapeHtml(emptyMessage)}</p></section>`
      : "";
  }

  const shownItems = items.slice(0, limit);
  const hiddenCount = items.length - shownItems.length;
  const listItems = shownItems
    .map((item) => `<li class="result-list__item"><span>${escapeHtml(item)}</span></li>`)
    .join("")
    + (hiddenCount > 0 ? `<li class="result-list__more">and ${hiddenCount} more</li>` : "");

  return `
    <section class="result-section">
      <h3>${escapeHtml(title)}</h3>
      <ul class="result-list">${listItems}</ul>
    </section>
  `;
}

function renderPathSection(title, pathValue, copyLabel) {
  if (!pathValue) {
    return "";
  }

  return `
    <section class="result-section">
      <h3>${escapeHtml(title)}</h3>
      <div class="result-path">
        <code>${escapeHtml(pathValue)}</code>
        <button class="copy-button" type="button" data-copy="${escapeHtml(pathValue)}" aria-label="${escapeHtml(copyLabel)}">Copy</button>
      </div>
    </section>
  `;
}

function renderSummaryRows(rows) {
  const populatedRows = rows.filter((row) => row.value !== null && row.value !== undefined && row.value !== "");

  if (populatedRows.length === 0) {
    return "";
  }

  return `
    <dl class="result-summary-grid">
      ${populatedRows
        .map(
          (row) => `
            <div class="result-summary-row">
              <dt>${escapeHtml(row.label)}</dt>
              <dd>${escapeHtml(row.value)}</dd>
            </div>
          `,
        )
        .join("")}
    </dl>
  `;
}

function renderResultCard(container, {
  tone = "neutral",
  badgeLabel = "Status",
  message = "",
  notes = [],
  summaryRows = [],
  sections = [],
} = {}) {
  const noteItems = notes
    .filter(Boolean)
    .map((note) => `<li>${escapeHtml(note)}</li>`)
    .join("");

  container.innerHTML = `
    <div class="result-card__header">
      <span class="result-badge result-badge--${escapeHtml(tone)}">${escapeHtml(badgeLabel)}</span>
      <p class="result-message">${escapeHtml(message)}</p>
    </div>
    ${noteItems ? `<ul class="result-notes">${noteItems}</ul>` : ""}
    ${renderSummaryRows(summaryRows)}
    <div class="result-sections">${sections.filter(Boolean).join("")}</div>
  `;
}

function describeFoundImages(imageCount, fullSheets) {
  if (fullSheets === 0) {
    return `Found ${pluralize(imageCount, "image")}: not enough to fill a sheet of ${IMAGES_PER_SHEET}.`;
  }

  const leftOver = imageCount - fullSheets * IMAGES_PER_SHEET;
  return `Found ${pluralize(imageCount, "image")}: enough for ${pluralize(fullSheets, "full sheet")}${leftOver > 0 ? `, with ${leftOver} left over` : ""}.`;
}

// Said before anything is made, because by default left-over images are skipped.
function describeLeftOverTip(imageCount, fullSheets) {
  if (imageCount - fullSheets * IMAGES_PER_SHEET <= 0) {
    return "";
  }

  return fullSheets === 0
    ? `Tick ${PART_FILLED_OPTION} in step 3 to make a sheet anyway.`
    : `Left-over images are skipped unless you tick ${PART_FILLED_OPTION} in step 3.`;
}

function renderScanSummary(result) {
  const imageCount = result.image_count ?? 0;
  const fullSheets = result.estimated_pages ?? 0;
  const availableSubfolders = Array.isArray(result.available_subfolders)
    ? result.available_subfolders.map(normalizeSubfolderOption).filter(Boolean)
    : [];
  const folderNames = availableSubfolders.map(({ displayName }) => displayName);
  const sampleFiles = Array.isArray(result.sample_files) ? result.sample_files : [];
  const isBatchMode = generationState.mode === "batch";

  // A folder of bundles has no images of its own: finding bundles inside is
  // the good outcome there, not a problem.
  if (isBatchMode && availableSubfolders.length > 0) {
    renderResultCard(scanResultEl, {
      tone: "success",
      badgeLabel: "Bundles found",
      message: `Found ${pluralize(availableSubfolders.length, "bundle folder")}.`,
      sections: [renderListSection("Bundles", folderNames)],
    });
    return;
  }

  // Each mode pointed at the other mode's kind of folder: say which mode fits.
  if (!isBatchMode && !result.valid && availableSubfolders.length > 0) {
    renderResultCard(scanResultEl, {
      tone: "warning",
      badgeLabel: "Pick a folder",
      message: `No images here, but there ${availableSubfolders.length === 1 ? "is 1 folder" : `are ${availableSubfolders.length} folders`} inside.`,
      notes: ["Pick one in step 1, or switch to “Many bundles” to make images for each of them."],
      sections: [renderListSection("Folders inside", folderNames)],
    });
    return;
  }

  if (isBatchMode && result.valid) {
    renderResultCard(scanResultEl, {
      tone: "warning",
      badgeLabel: "Needs attention",
      message: `This folder has ${pluralize(imageCount, "image")} but no bundle folders inside.`,
      notes: ["Switch to “One bundle” to make images from it."],
    });
    return;
  }

  if (!result.valid) {
    renderResultCard(scanResultEl, {
      tone: "warning",
      badgeLabel: "Needs attention",
      message: result.message || "This folder can't be used yet.",
    });
    return;
  }

  renderResultCard(scanResultEl, {
    tone: "success",
    badgeLabel: "Ready",
    message: describeFoundImages(imageCount, fullSheets),
    notes: [describeLeftOverTip(imageCount, fullSheets)],
    sections: [renderListSection("First few files", sampleFiles)],
  });
}

function describeLeftOutImages(count) {
  if (!(count > 0)) {
    return "";
  }

  return count === 1
    ? `1 image didn't fill a sheet, so it was left out. Tick ${PART_FILLED_OPTION} to keep it.`
    : `${count} images didn't fill a sheet, so they were left out. Tick ${PART_FILLED_OPTION} to keep them.`;
}

// A video that fails does not fail the sheets: the server explains it at the
// end of its message, which is the part worth showing.
function describeVideoProblem(message) {
  const start = typeof message === "string" ? message.indexOf("Preview video was requested") : -1;
  return start >= 0 ? message.slice(start) : "The preview video couldn't be made.";
}

function renderBatchFolderOutcomeSection(results, kind) {
  if (!Array.isArray(results) || results.length === 0) {
    return "";
  }

  const requestedPreviewVideo = kind !== "cover" && Boolean(createPreviewVideoEl?.checked);
  const lines = results.map((result) => {
    const folderName = result.folder_name || result.displayName || fileName(result.output_path || "") || "Bundle";
    if (!result.success) {
      return `${folderName}: ${result.message || "failed."}`;
    }

    if (kind === "cover") {
      const outputFiles = Array.isArray(result.output_files) ? result.output_files : [];
      return `${folderName}: ${outputFiles.length > 0 ? outputFiles.map(fileName).join(", ") : "cover made"}`;
    }

    if ((result.pages_generated ?? 0) === 0) {
      return `${folderName}: no sheets made. ${result.message || ""}`.trim();
    }

    const sheets = pluralize(result.pages_generated, "sheet");
    if (result.video_created) {
      return `${folderName}: ${sheets} and a video`;
    }

    return requestedPreviewVideo ? `${folderName}: ${sheets}, but no video. ${describeVideoProblem(result.message)}` : `${folderName}: ${sheets}`;
  });

  return renderListSection("Each bundle", lines, "", { limit: Infinity });
}

function renderBatchSummary(result, kind) {
  const bundleResults = Array.isArray(result.bundle_results) ? result.bundle_results : [];
  const isCover = kind === "cover";
  // A bundle counts as done when something was made for it.
  const doneResults = bundleResults.filter((bundleResult) => bundleResult?.success && (isCover || (bundleResult.pages_generated ?? 0) > 0));
  const doneCount = doneResults.length;
  const totalCount = result.processed_folders ?? bundleResults.length;
  const outputName = isCover ? "covers" : "preview sheets";
  const requestedPreviewVideo = !isCover && Boolean(createPreviewVideoEl?.checked);
  const sum = (field) => doneResults.reduce((total, bundleResult) => total + (bundleResult[field] ?? 0), 0);

  let badgeLabel = "Done";
  let message = `Made ${outputName} for ${pluralize(doneCount, "bundle")}.`;
  if (doneCount === 0) {
    badgeLabel = "Nothing made";
    message = `Couldn't make ${outputName} for ${totalCount === 1 ? "the bundle" : `any of the ${totalCount} bundles`}.`;
  } else if (doneCount < totalCount) {
    badgeLabel = "Partly done";
    message = `Made ${outputName} for ${doneCount} of ${pluralize(totalCount, "bundle")}.`;
  }

  renderResultCard(generationResultEl, {
    tone: doneCount > 0 && doneCount === totalCount ? "success" : "warning",
    badgeLabel,
    message,
    summaryRows: isCover
      ? [
        { label: "Bundles done", value: `${doneCount} of ${totalCount}` },
        { label: "Cover files", value: pluralize(doneResults.flatMap((bundleResult) => bundleResult.output_files ?? []).length, "file") },
      ]
      : [
        { label: "Bundles done", value: `${doneCount} of ${totalCount}` },
        { label: "Sheets", value: pluralize(sum("pages_generated"), "sheet") },
        { label: "Images used", value: pluralize(sum("total_images"), "image") },
        { label: "Videos", value: requestedPreviewVideo ? pluralize(bundleResults.filter((bundleResult) => bundleResult.video_created).length, "video") : null },
      ],
    sections: [
      renderBatchFolderOutcomeSection(bundleResults, kind),
      renderPathSection("Saved in", result.created_output_root_path || "", "Copy the folder path"),
    ],
  });
}

function renderGenerationSummary(result, kind = "sheets") {
  if (Array.isArray(result.bundle_results)) {
    renderBatchSummary(result, kind);
    return;
  }

  const outputFiles = Array.isArray(result.output_files) ? result.output_files : [];
  const pagesGenerated = result.pages_generated ?? 0;
  const totalImages = result.total_images ?? 0;
  const outputPath = result.output_path || "";
  const pageSizeRow = { label: "Page size", value: result.page_geometry || null };

  if (kind === "cover") {
    const coverMade = outputFiles.length > 0;
    renderResultCard(generationResultEl, {
      tone: coverMade ? "success" : "warning",
      badgeLabel: coverMade ? "Done" : "Nothing made",
      message: coverMade ? `Made a cover from ${pluralize(totalImages, "image")}.` : result.message || "No cover was made.",
      summaryRows: [pageSizeRow],
      sections: [
        renderListSection("Files", outputFiles.map(fileName)),
        renderPathSection("Saved in", outputPath, "Copy the folder path"),
      ],
    });
    return;
  }

  const videoFilePath = result.video_file || "";
  const requestedPreviewVideo = Boolean(createPreviewVideoEl?.checked);
  const notes = [
    describeLeftOutImages(result.images_dropped ?? 0),
    result.images_skipped > 0 ? `Skipped ${pluralize(result.images_skipped, "file")} that couldn't be read.` : "",
    result.backgrounds_cleaned > 0 ? `Cleaned the background on ${pluralize(result.backgrounds_cleaned, "image")}.` : "",
  ];
  if (requestedPreviewVideo && !videoFilePath) {
    notes.push(pagesGenerated > 0 ? describeVideoProblem(result.message) : "With no sheets, there was nothing to put in a video.");
  }

  renderResultCard(generationResultEl, {
    tone: pagesGenerated > 0 ? "success" : "warning",
    badgeLabel: pagesGenerated > 0 ? "Done" : "Nothing made",
    message: pagesGenerated > 0
      ? `Made ${pluralize(pagesGenerated, "preview sheet")} from ${pluralize(totalImages, "image")}${videoFilePath ? ", plus a preview video" : ""}.`
      : "No sheets were made.",
    notes,
    summaryRows: pagesGenerated > 0 ? [pageSizeRow] : [],
    sections: [
      renderListSection("Files", outputFiles.map(fileName)),
      renderPathSection("Preview video", videoFilePath, "Copy the video path"),
      pagesGenerated > 0 ? renderPathSection("Saved in", outputPath, "Copy the folder path") : "",
    ],
  });
}

function renderPendingResult(container, badgeLabel, message) {
  renderResultCard(container, {
    tone: "neutral",
    badgeLabel,
    message,
  });
}

function renderFailedResult(container, message) {
  renderResultCard(container, {
    tone: "warning",
    badgeLabel: "Failed",
    message,
  });
}

// Lets a scan that never got an answer flow through the normal "not ready" path.
function buildFailedScanResult(message) {
  return {
    valid: false,
    image_count: 0,
    sample_files: [],
    estimated_pages: 0,
    available_subfolders: [],
    message,
  };
}

generationModeEls.forEach((modeEl) => {
  modeEl.addEventListener("change", (event) => {
    generationState.mode = event.target.value;
    resetSingleFolderSelectionState();
    syncDerivedOutputPath();
    resetScanReadyState();
    renderPendingResult(scanResultEl, "Waiting", generationState.mode === "batch"
      ? "Scan the folder of bundles to continue."
      : "Scan the folder to continue.");
    renderPendingResult(generationResultEl, "Waiting", "Nothing made yet. Your files will be listed here.");
    applyGenerationMode();
  });
});

backgroundCleanModeEl?.addEventListener("change", updateBackgroundCleanControls);

// Paths are long and fiddly to select by hand.
document.addEventListener("click", async (event) => {
  const button = event.target.closest?.(".copy-button");
  if (!button) {
    return;
  }

  const idleText = "Copy";
  try {
    await navigator.clipboard.writeText(button.dataset.copy || "");
    button.textContent = "Copied!";
  } catch {
    // No clipboard on plain http:// other than localhost: select the path
    // instead, ready to copy.
    const pathEl = button.parentElement?.querySelector("code");
    if (pathEl) {
      window.getSelection()?.selectAllChildren(pathEl);
    }
    button.textContent = "Selected";
  }
  setTimeout(() => {
    button.textContent = idleText;
  }, 1800);
});

createPreviewVideoEl?.addEventListener("change", () => {
  updatePreviewVideoControls();
  recomputeStepFiveState();
});

async function scanCurrentFolder({ preserveSubfolderPicker = false } = {}) {
  const selectedSubfolder = preserveSubfolderPicker && generationState.mode === "single" ? generationState.selectedWorkingFolder : "";
  const selectedBatchFolders = preserveSubfolderPicker && generationState.mode === "batch" ? [...generationState.selectedBatchFolders] : [];

  if (!preserveSubfolderPicker) {
    clearSelectedWorkingFolder();
    setAvailableSubfolders([]);
    setSelectedBatchFolders([]);
    hideSubfolderPicker({ preserveOptions: false });
    resetCoverCollageIncludeList();
  }
  resetBatchValidationState();
  resetScanReadyState();
  renderPendingResult(scanResultEl, "Scanning", generationState.mode === "batch" ? "Looking for bundle folders…" : "Counting images…");

  const { ok, data, errorMessage } = await postJson("/api/jobs/scan-folder", { folder_path: readMainInputFolderPath() });
  const result = ok ? data : buildFailedScanResult(errorMessage);
  renderScanSummary(result);
  const scannedFolderPath = readMainInputFolderPath();
  setScannedRootFolder(scannedFolderPath);
  setOutputDerivationSourceFolder(scannedFolderPath);
  syncDerivedOutputPath();
  setScanReadyState(Boolean(result.valid));
  if (generationState.mode === "batch") {
    setBatchParentScanComplete(true);
  }

  if (Array.isArray(result.available_subfolders) && result.available_subfolders.length > 0) {
    // Making images for every bundle is the usual case, so a fresh list starts
    // with all of them picked; a re-scan keeps the user's picks.
    generationState.selectedBatchFolders = generationState.mode === "batch" && selectedBatchFolders.length === 0
      ? result.available_subfolders.map(normalizeSubfolderOption).filter(Boolean).map(({ fullPath }) => fullPath)
      : selectedBatchFolders;
    showSubfolderPicker(result.available_subfolders, selectedSubfolder);
  } else {
    clearSelectedWorkingFolder();
    setAvailableSubfolders([]);
    setSelectedBatchFolders([]);
    hideSubfolderPicker({ preserveOptions: false });
  }

  return result;
}

async function scanFolderAndCheckBundles() {
  await scanCurrentFolder({ preserveSubfolderPicker: true });
  // Check the picked bundles straight away, so making images for all the
  // bundles in a folder takes one click.
  if (generationState.mode === "batch" && hasSelectedBatchFolders()) {
    await validateSelectedBatchFolders();
  }
}

scanButton?.addEventListener("click", async () => {
  await runExclusive(scanFolderAndCheckBundles);
});

// The check card describes the picked bundles, so it follows the picks:
// unticking the bundle that failed turns it ready without a new check.
function renderBatchCheckSummary() {
  const selectedPaths = getSelectedBatchFolderPaths();
  if (selectedPaths.length === 0) {
    renderPendingResult(scanResultEl, "Pick bundles", "Pick at least one bundle to check.");
    return;
  }

  const selectedPathSet = new Set(selectedPaths);
  const results = generationState.batchValidationResults.filter((result) => selectedPathSet.has(result.folderPath));
  const readyResults = results.filter((result) => result.valid);
  const invalidResults = results.filter((result) => !result.valid);
  const uncheckedCount = selectedPaths.length - results.length;

  let tone = "success";
  let badgeLabel = "Ready";
  let message = readyResults.length === 1 ? "The picked bundle is ready." : `All ${readyResults.length} picked bundles are ready.`;
  if (invalidResults.length > 0) {
    tone = "warning";
    badgeLabel = "Needs attention";
    message = `${invalidResults.length} of ${pluralize(selectedPaths.length, "picked bundle")} ${invalidResults.length === 1 ? "needs" : "need"} attention.`;
  } else if (uncheckedCount > 0) {
    tone = "neutral";
    badgeLabel = "Not checked";
    message = `${pluralize(uncheckedCount, "picked bundle")} ${uncheckedCount === 1 ? "hasn't" : "haven't"} been checked yet.`;
  }

  renderResultCard(scanResultEl, {
    tone,
    badgeLabel,
    message,
    notes: [invalidResults.length > 0 && invalidResults.length < selectedPaths.length
      ? "Untick the ones that need attention to go ahead with the rest."
      : ""],
    summaryRows: [
      { label: "Ready", value: pluralize(readyResults.length, "bundle") },
      { label: "Images", value: pluralize(readyResults.reduce((sum, result) => sum + (result.image_count ?? 0), 0), "image") },
      { label: "Full sheets", value: pluralize(readyResults.reduce((sum, result) => sum + (result.estimated_pages ?? 0), 0), "sheet") },
    ],
    sections: [
      renderListSection(
        "Ready",
        readyResults.map((result) => `${result.displayName} (${pluralize(result.image_count ?? 0, "image")})`),
        "None of them are ready yet.",
      ),
      renderListSection(
        "Need attention",
        invalidResults.map((result) => `${result.displayName}: ${result.message || "Not ready"}`),
        "",
        { limit: Infinity },
      ),
    ],
  });
}

async function validateSelectedBatchFolders() {
  if (generationState.mode !== "batch") {
    return [];
  }

  const selectedBatchFolders = getSelectedBatchFolderPaths();
  if (!generationState.batchParentScanComplete) {
    renderPendingResult(scanResultEl, "Scan first", "Scan the folder of bundles first.");
    return [];
  }

  if (selectedBatchFolders.length === 0) {
    setBatchValidationResults([]);
    recomputeStepFiveState();
    renderPendingResult(scanResultEl, "Pick bundles", "Pick at least one bundle to check.");
    return [];
  }

  renderPendingResult(scanResultEl, "Scanning", `Checking ${pluralize(selectedBatchFolders.length, "bundle")}…`);

  const results = await Promise.all(selectedBatchFolders.map(async (folderPath) => {
    const { ok, data, errorMessage } = await postJson("/api/jobs/scan-folder", { folder_path: folderPath });
    const result = ok ? data : buildFailedScanResult(errorMessage);
    return {
      folderPath,
      displayName: generationState.availableSubfolders.find((subfolder) => subfolder.fullPath === folderPath)?.displayName || folderPath,
      ...result,
    };
  }));

  setBatchValidationResults(results);
  renderBatchCheckSummary();

  recomputeStepFiveState();
  return results;
}

batchScanButton?.addEventListener("click", async () => {
  await runExclusive(validateSelectedBatchFolders);
});

subfolderPickerEl?.addEventListener("change", () => {
  if (generationState.mode === "single") {
    clearSelectedWorkingFolder();
    recomputeStepFiveState();
  }
});

selectAllSubfoldersButton?.addEventListener("click", () => {
  setSelectedBatchFolders(generationState.availableSubfolders.map(({ fullPath }) => fullPath));
  applyBatchSelectionChange();
  syncBatchSelectionUI();
});

clearSubfolderSelectionButton?.addEventListener("click", () => {
  setSelectedBatchFolders([]);
  applyBatchSelectionChange();
  syncBatchSelectionUI();
});

useSubfolderButton?.addEventListener("click", async () => {
  if (!subfolderPickerEl.value || generationState.busy) {
    return;
  }

  // Scan the chosen folder as if it had been typed in: the scan is what makes
  // it ready, and the input then shows where the images come from.
  inputFolderEl.value = subfolderPickerEl.value;
  resetSingleFolderSelectionState();
  syncDerivedOutputPath();
  await runExclusive(() => scanCurrentFolder());
});

// The folder browser. A page can't learn the path of a folder picked with the
// browser's own file chooser, so this one lists folders through Pasteup:
// clicking a folder opens it, and "Use this folder" takes the one shown.
const folderBrowserState = {
  path: "",
  parentPath: null,
  breadcrumbs: [],
  // Where browsing got to last time, to start from when no path is typed.
  lastPath: "",
  // Only the latest listing is drawn, so a slow one can't replace a newer one.
  requestId: 0,
};

function openFolderBrowser() {
  if (!folderBrowserEl || folderBrowserEl.open || generationState.busy) {
    return;
  }

  folderBrowserTitleEl.textContent = `Choose the ${getSelectedGenerationModeConfig().inputLabel.toLowerCase()}`;
  folderBrowserState.path = "";
  folderBrowserState.parentPath = null;
  folderBrowserState.breadcrumbs = [];
  folderBrowserPlacesEl.replaceChildren();
  folderBrowserCrumbsEl.replaceChildren();
  folderBrowserListEl.replaceChildren();
  showFolderBrowserNotice("");
  folderBrowserStatusEl.textContent = "Opening…";
  folderBrowserChooseButton.disabled = true;
  folderBrowserEl.showModal();
  // A typed path is where browsing starts, so it works as a shortcut too.
  showFolderInBrowser(readMainInputFolderPath() || folderBrowserState.lastPath);
}

async function showFolderInBrowser(folderPath, { focusPath = "" } = {}) {
  const requestId = ++folderBrowserState.requestId;
  folderBrowserListEl.setAttribute("aria-busy", "true");
  const { ok, data, errorMessage } = await postJson("/api/jobs/browse-folder", { folder_path: folderPath });
  if (requestId !== folderBrowserState.requestId) {
    return;
  }

  folderBrowserListEl.setAttribute("aria-busy", "false");
  if (!ok) {
    showFolderBrowserNotice(errorMessage);
    if (!folderBrowserState.path) {
      folderBrowserStatusEl.textContent = "";
    }
    return;
  }

  renderFolderBrowser(data, focusPath);
}

function renderFolderBrowser(listing, focusPath = "") {
  const folders = Array.isArray(listing.folders) ? listing.folders : [];
  const breadcrumbs = Array.isArray(listing.breadcrumbs) ? listing.breadcrumbs : [];
  const places = Array.isArray(listing.places) ? listing.places : [];
  folderBrowserState.path = listing.path;
  folderBrowserState.lastPath = listing.path;
  folderBrowserState.parentPath = listing.parent_path || null;
  folderBrowserState.breadcrumbs = breadcrumbs;

  folderBrowserPlacesEl.replaceChildren(...places.map((place) => {
    const button = createFolderButton(place, "folder-browser__place");
    if (place.path === listing.path) {
      button.setAttribute("aria-current", "true");
    }
    return wrapInListItem(button);
  }));

  folderBrowserCrumbsEl.replaceChildren(...breadcrumbs.map((crumb, index) => {
    if (index < breadcrumbs.length - 1) {
      return wrapInListItem(createFolderButton(crumb, "folder-browser__crumb"));
    }

    const here = document.createElement("span");
    here.className = "folder-browser__here";
    here.setAttribute("aria-current", "location");
    here.textContent = crumb.name;
    return wrapInListItem(here);
  }));

  folderBrowserListEl.setAttribute("aria-label", `Folders inside ${breadcrumbs.at(-1)?.name || listing.path}`);
  if (folders.length > 0) {
    folderBrowserListEl.replaceChildren(...folders.map((folder) => wrapInListItem(createFolderButton(folder, "folder-browser__folder"))));
  } else {
    const emptyItem = document.createElement("li");
    emptyItem.className = "folder-browser__empty";
    emptyItem.textContent = "No folders inside.";
    folderBrowserListEl.replaceChildren(emptyItem);
  }
  folderBrowserListEl.scrollTop = 0;

  showFolderBrowserNotice(listing.message || "");
  folderBrowserStatusEl.textContent = describeFolderContents(listing.image_count ?? 0, folders.length);
  folderBrowserChooseButton.disabled = false;

  // Keyboard focus stays in the list: on the folder just come up out of, or
  // else the first. Only that one is in the tab order; arrow keys move on.
  const folderButtons = [...folderBrowserListEl.querySelectorAll("button")];
  const focusTarget = folderButtons.find((button) => button.dataset.path === focusPath) || folderButtons[0];
  folderButtons.forEach((button) => {
    button.tabIndex = button === focusTarget ? 0 : -1;
  });
  (focusTarget || folderBrowserChooseButton).focus();
}

function createFolderButton({ name, path }, className) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.dataset.path = path;
  button.textContent = name;
  return button;
}

function wrapInListItem(child) {
  const item = document.createElement("li");
  item.append(child);
  return item;
}

function showFolderBrowserNotice(message) {
  folderBrowserNoticeEl.textContent = message;
  folderBrowserNoticeEl.hidden = !message;
}

function describeFolderContents(imageCount, folderCount) {
  const images = imageCount > 0 ? pluralize(imageCount, "image") : "";
  const folders = folderCount > 0 ? pluralize(folderCount, "folder") : "";
  if (images && folders) {
    return `${images} and ${folders} here.`;
  }
  if (images) {
    return `${images} here.`;
  }
  return folders ? `${folders} here, no images.` : "No images or folders here.";
}

// Going up to a folder on the current path lands on the folder just left.
function childOnCurrentPath(folderPath) {
  const { breadcrumbs } = folderBrowserState;
  const index = breadcrumbs.findIndex((crumb) => crumb.path === folderPath);
  return index >= 0 && index < breadcrumbs.length - 1 ? breadcrumbs[index + 1].path : "";
}

async function useBrowsedFolder() {
  const chosenPath = folderBrowserState.path;
  if (!chosenPath || generationState.busy) {
    return;
  }

  folderBrowserEl.close();
  // As if the path had been typed in, then scanned.
  inputFolderEl.value = chosenPath;
  // A long path shows its end, the folder's own name, rather than its start.
  inputFolderEl.scrollLeft = inputFolderEl.scrollWidth;
  resetSingleFolderSelectionState();
  syncDerivedOutputPath();
  resetScanReadyState();
  resetCoverCollageIncludeList();
  await runExclusive(scanFolderAndCheckBundles);
  // The scan disables Browse, which drops keyboard focus back to the page.
  if (document.activeElement === document.body) {
    browseFolderButton?.focus();
  }
}

browseFolderButton?.addEventListener("click", openFolderBrowser);
folderBrowserCancelButton?.addEventListener("click", () => folderBrowserEl.close());
folderBrowserChooseButton?.addEventListener("click", useBrowsedFolder);

// Places, the path and the folders are all buttons carrying the folder they open.
folderBrowserEl?.addEventListener("click", (event) => {
  const button = event.target.closest?.("button[data-path]");
  if (button) {
    showFolderInBrowser(button.dataset.path, { focusPath: childOnCurrentPath(button.dataset.path) });
  }
});

folderBrowserEl?.addEventListener("keydown", (event) => {
  // Backspace goes up a level, as in a file manager.
  if (event.key === "Backspace" && folderBrowserState.parentPath) {
    event.preventDefault();
    showFolderInBrowser(folderBrowserState.parentPath, { focusPath: folderBrowserState.path });
    return;
  }

  const folderButtons = [...folderBrowserListEl.querySelectorAll("button")];
  const index = folderButtons.indexOf(document.activeElement);
  const nextIndex = { ArrowDown: index + 1, ArrowUp: index - 1, Home: 0, End: folderButtons.length - 1 }[event.key];
  if (index < 0 || nextIndex === undefined) {
    return;
  }

  event.preventDefault();
  const next = folderButtons[Math.min(Math.max(nextIndex, 0), folderButtons.length - 1)];
  folderButtons[index].tabIndex = -1;
  next.tabIndex = 0;
  next.focus();
});

// A listing still on its way when the browser closes is dropped.
folderBrowserEl?.addEventListener("close", () => {
  folderBrowserState.requestId += 1;
});

async function runCoverCollage() {
  const selectedTemplateLabel = readSelectedCoverCollageTemplateLabel();

  if (generationState.mode !== "batch") {
    renderPendingResult(generationResultEl, "Working", `Making a ${selectedTemplateLabel.toLowerCase()} cover…`);
    revealResult(generationResultEl);

    const { ok, data: result, errorMessage } = await postJson("/api/jobs/generate-cover-collage", readCoverCollagePayload());
    if (!ok) {
      renderFailedResult(generationResultEl, errorMessage);
      return;
    }

    renderGenerationSummary(result, "cover");
    return;
  }

  const payload = buildBatchCoverCollagePayload();
  if (payload.selected_subfolders.length === 0 || !hasValidatedBatchSelection()) {
    renderPendingResult(generationResultEl, "Check bundles", "Check the picked bundles before making covers.");
    return;
  }

  renderPendingResult(generationResultEl, "Working", `Making ${selectedTemplateLabel.toLowerCase()} covers for ${pluralize(payload.selected_subfolders.length, "bundle")}…`);
  revealResult(generationResultEl);

  const { ok, data: batchResult, errorMessage } = await postJson("/api/jobs/generate-cover-collage-batch", payload);
  if (!ok) {
    renderFailedResult(generationResultEl, errorMessage);
    return;
  }

  renderGenerationSummary(batchResult, "cover");
}

coverCollageButton?.addEventListener("click", async () => {
  if (coverCollageButton.disabled) {
    return;
  }

  await runExclusive(runCoverCollage);
});

generateButton?.addEventListener("click", async () => {
  if (generateButton.disabled) {
    return;
  }

  if (!validateVideoGenerationSettings()) {
    return;
  }

  if (!validateOutputQualitySettings()) {
    return;
  }

  if (generationState.mode === "batch") {
    const { availableCount, selectedCount } = getBatchGenerationSelectionDetails();
    if (availableCount === 0) {
      renderPendingResult(generationResultEl, "Scan first", "Scan a folder that has bundle folders inside.");
      updateBatchSelectionStatus();
      return;
    }

    if (selectedCount === 0) {
      renderPendingResult(generationResultEl, "Pick bundles", "Pick at least one bundle, then check it.");
      updateBatchSelectionStatus();
      return;
    }

    if (!generationState.batchValidationReady || !hasValidatedBatchSelection()) {
      renderPendingResult(generationResultEl, "Check bundles", "Check the picked bundles before making images.");
      updateBatchSelectionStatus();
      return;
    }
  }

  await runExclusive(runPageGeneration);
});

async function runPageGeneration() {
  const config = getSelectedGenerationModeConfig();
  renderPendingResult(generationResultEl, "Working", getGenerationStatusMessage());
  revealResult(generationResultEl);

  const { ok, data: result, errorMessage } = await postJson(config.endpoint, config.payload());
  if (!ok) {
    renderFailedResult(generationResultEl, errorMessage);
    return;
  }

  renderGenerationSummary(result, "sheets");
}

updatePreviewVideoControls();
updateBackgroundCleanControls();
hideSubfolderPicker();
applyGenerationMode();
syncDerivedOutputPath();

inputFolderEl?.addEventListener("input", () => {
  resetSingleFolderSelectionState();
  syncDerivedOutputPath();
  resetScanReadyState();
  resetCoverCollageIncludeList();
});
inputFolderEl?.addEventListener("change", () => {
  resetSingleFolderSelectionState();
  syncDerivedOutputPath();
  resetCoverCollageIncludeList();
});
outputFolderEl?.addEventListener("input", resetScanReadyState);
