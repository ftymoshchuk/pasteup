const THEME_STORAGE_KEY = "pasteup-theme";
const GENERATION_MODES = {
  single: {
    inputLabel: "Input folder",
    outputLabel: "Output folder",
    endpoint: "/api/jobs/generate",
    payload: () => ({
      folder_path: readWorkingFolderPath(),
      output_path: outputFolderEl.value.trim(),
      ...readCommonGenerationSettings(),
    }),
    statusMessage: "Running page generation...",
    buttonText: "Run page generation",
    helpText: "Single folder is best when you already know exactly which image folder you want to process.",
    modeStepCopy: "Choose Single folder for one image set, or Batch folders to process each image folder inside a parent directory.",
    folderStepCopy: "Enter the folder to inspect and the folder where completed output should be saved.",
    outputStepCopy: "After a successful scan, create pages from the current folder or build a cover collage with the template that best fits your overview image.",
    outputHintReady: "Scan complete. You can now run page generation or build a cover collage template for this folder.",
  },
  batch: {
    inputLabel: "Parent folder",
    outputLabel: "Created output root",
    endpoint: "/api/jobs/generate-all-folders",
    payload: () => readBatchFolderPayload(),
    statusMessage: "Running batch page generation for the validated selected folders...",
    buttonText: "Generate pages for selected batch folders",
    helpText: "Batch folders is best when one parent folder contains several image folders you want to process together.",
    modeStepCopy: "Batch folders scans a parent directory first so eligible child folders appear for review before you generate output.",
    folderStepCopy: "Enter the parent folder to inspect and the shared created-output root where generated child folders should be written after you scan the parent folder, choose the batch folders to include, and scan the selected batch folders.",
    outputStepCopy: "After you scan the parent folder, review the eligible child folders, validate the selected folders, then run batch page generation or batch cover-collage generation for that validated selection.",
    outputHintReady: "Selected batch folders scanned successfully. You can now run batch page generation or batch cover-collage generation for the validated selection.",
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
const themeToggleButton = document.getElementById("theme-toggle");
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
    return { ok: false, data: null, errorMessage: `Could not reach the app server. Is it still running? (${error.message})` };
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
  recomputeStepFiveState();
}

// Print resolution and background cleaning. Kept separate from the video
// settings so the cover-collage payloads, which enumerate their fields rather
// than spreading everything, can pick these up without also sending video keys
// their endpoint does not accept.
function readOutputQualitySettings() {
  return {
    page_unit: pageUnitEl?.value || "px",
    dpi: Number(dpiEl?.value) || 300,
    background_clean_mode: backgroundCleanModeEl?.value || "off",
    background_tolerance: Number(backgroundToleranceEl?.value ?? 240),
    background_feather: Number(backgroundFeatherEl?.value ?? 1),
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
    duration_seconds: Number(videoDurationSecondsEl?.value),
    transition: videoTransitionEl?.value || "none",
  };
}

function validateVideoGenerationSettings() {
  const commonSettings = readCommonGenerationSettings();
  const maxDurationSeconds = Number(videoDurationSecondsEl?.max) || 120;

  if (!(commonSettings.duration_seconds > 0) || commonSettings.duration_seconds > maxDurationSeconds) {
    renderPendingResult(generationResultEl, "Invalid settings", `Duration must be greater than 0 and at most ${maxDurationSeconds} seconds.`);
    return false;
  }

  return true;
}

function validateOutputQualitySettings() {
  const quality = readOutputQualitySettings();

  if (!Number.isFinite(quality.dpi) || quality.dpi <= 0 || quality.dpi > 1200) {
    renderPendingResult(generationResultEl, "Invalid settings", "DPI must be between 1 and 1200.");
    return false;
  }

  if (quality.background_tolerance < 0 || quality.background_tolerance > 255) {
    renderPendingResult(generationResultEl, "Invalid settings", "Background tolerance must be between 0 and 255.");
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
  const selectedPaths = getSelectedBatchFolderPaths();
  generationState.validatedBatchSelectionSignature = generationState.batchValidationResults.length > 0
    ? getBatchSelectionSignature(selectedPaths)
    : "";
  generationState.batchValidationReady = selectedPaths.length > 0
    && generationState.validatedBatchFolders.length === selectedPaths.length
    && generationState.validatedBatchSelectionSignature === getBatchSelectionSignature(selectedPaths);
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
    return "Run the parent-folder scan first to discover detected child folders for batch mode.";
  }

  if (availableCount === 0) {
    return "No detected child folders are available yet. Run a scan on a parent folder to load batch options.";
  }

  if (selectedCount === 0) {
    return `No folders selected. Choose all ${availableCount} detected child folders or select at least one before running the selected-folder scan.`;
  }

  if (!hasValidatedBatchSelection()) {
    return `Selected ${selectedCount} detected ${selectedCount === 1 ? "batch folder" : "batch folders"}. Run Scan selected folders successfully for this exact selection before page generation.`;
  }

  const validatedSelectedCount = selectedCount;

  if (isAllSelected) {
    return `Selected batch folders scanned successfully. Ready to generate pages for all ${availableCount} validated batch folders.`;
  }

  return `Selected batch folders scanned successfully. Ready to generate pages for ${validatedSelectedCount} validated ${validatedSelectedCount === 1 ? "batch folder" : "batch folders"}.`;
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
    return previewVideoEnabled ? "Run page generation + preview video" : getSelectedGenerationModeConfig().buttonText;
  }

  const { selectedCount } = getBatchGenerationSelectionDetails();

  if (selectedCount === 0) {
    return previewVideoEnabled
      ? "Generate pages + preview video for selected batch folders"
      : "Generate pages for selected batch folders";
  }

  if (selectedCount === 1) {
    return previewVideoEnabled
      ? "Generate pages + preview video for 1 selected batch folder"
      : "Generate pages for 1 selected batch folder";
  }

  return previewVideoEnabled
    ? `Generate pages + preview video for ${selectedCount} selected batch folders`
    : `Generate pages for ${selectedCount} selected batch folders`;
}

function updatePreviewVideoControls() {
  const previewVideoEnabled = Boolean(createPreviewVideoEl?.checked);

  if (videoDurationSecondsEl) {
    videoDurationSecondsEl.disabled = !previewVideoEnabled;
  }

  if (videoTransitionEl) {
    videoTransitionEl.disabled = !previewVideoEnabled;
  }

  if (createPreviewVideoHelpEl) {
    createPreviewVideoHelpEl.innerHTML = previewVideoEnabled
      ? "Preview video is enabled. Click <strong>Generate pages</strong> to create pages and the video together."
      : "Enable this, then click <strong>Generate pages</strong>. Video creation runs as part of page generation.";
  }
}

function getCoverCollageButtonLabel() {
  if (generationState.mode !== "batch") {
    return "Build cover collage";
  }

  const { selectedCount } = getBatchGenerationSelectionDetails();

  if (selectedCount === 0) {
    return "Build cover collage for selected folders";
  }

  if (selectedCount === 1) {
    return "Build cover collage for 1 selected folder";
  }

  return `Build cover collage for ${selectedCount} selected folders`;
}

function getGenerationStatusMessage() {
  if (generationState.mode !== "batch") {
    return getSelectedGenerationModeConfig().statusMessage;
  }

  const { availableCount, selectedCount, isAllSelected } = getBatchGenerationSelectionDetails();
  if (availableCount === 0 || selectedCount === 0) {
    return "Running page generation for the validated selected batch folders from the detected batch list...";
  }

  if (isAllSelected) {
    return `Running page generation for all ${availableCount} validated ${availableCount === 1 ? "batch folder" : "batch folders"}...`;
  }

  return `Running page generation for the validated selected batch folders: ${selectedCount} ${selectedCount === 1 ? "batch folder" : "batch folders"}...`;
}

function getOutputActionsHint() {
  if (generationState.mode !== "batch") {
    if (!generationState.singleFolderReady) {
      return "Output actions stay disabled until the scan confirms the selected folder is ready.";
    }
    return getSelectedGenerationModeConfig().outputHintReady;
  }

  const { availableCount, selectedCount, isAllSelected } = getBatchGenerationSelectionDetails();
  if (!generationState.batchParentScanComplete) {
    return "Run the parent-folder scan first to discover available child folders for batch mode. Then choose folders and scan the selected batch folders before batch page or cover-collage generation.";
  }

  if (availableCount === 0) {
    return "Parent-folder scan complete, but no detected child folders are available for batch generation yet.";
  }

  if (selectedCount === 0) {
    return `Parent-folder scan complete. Select at least one of the ${availableCount} detected child folders, then run Scan selected folders to validate the chosen batch folders.`;
  }

  if (!hasValidatedBatchSelection()) {
    return `Batch output stays disabled because the current selection of ${selectedCount} ${selectedCount === 1 ? "batch folder has" : "batch folders have"} not been scanned successfully by Scan selected folders yet.`;
  }

  if (isAllSelected && availableCount > 1) {
    return `Selected batch folders scanned successfully. Batch page generation and batch cover-collage generation will run for all ${availableCount} selected validated batch folders.`;
  }

  if (selectedCount > 1) {
    return `Selected batch folders scanned successfully. Batch page generation and batch cover-collage generation are ready for the validated selection: ${selectedCount} batch folders.`;
  }

  if (!isCoverCollageReady()) {
    return "Selected batch folders scanned successfully. Batch page generation and batch cover-collage generation are ready for the one validated batch folder once output actions are enabled.";
  }

  return "Selected batch folders scanned successfully. Batch page generation and batch cover-collage generation are ready for the current validated batch selection.";
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
  [scanButton, batchScanButton].forEach((button) => {
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
    batchSelectionSummaryEl.textContent = "Run the parent-folder scan to discover child folders for this batch.";
    updateBatchSelectionStatus();
    return;
  }

  if (availableCount === 0) {
    batchSelectionSummaryEl.textContent = "No detected child folders are available yet.";
    updateBatchSelectionStatus();
    return;
  }

  if (selectedCount === 0) {
    batchSelectionSummaryEl.textContent = `Selected 0 of ${availableCount} detected child folders.`;
    updateBatchSelectionStatus();
    return;
  }

  const summarySuffix = selectedLabels.length > 0
    ? ` ${selectedLabels.join(", ")}`
    : "";
  batchSelectionSummaryEl.textContent = `Selected ${selectedCount} of ${availableCount} detected child folders.${summarySuffix}`;
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
    emptyState.textContent = "Run a scan on a parent folder to load detected child folders.";
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
      setBatchValidationResults([]);
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

function setTheme(theme) {
  const resolvedTheme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = resolvedTheme;
  localStorage.setItem(THEME_STORAGE_KEY, resolvedTheme);
  const isDark = resolvedTheme === "dark";
  const nextThemeLabel = isDark ? "soft light" : "terminal dark";
  const currentThemeLabel = isDark ? "terminal dark" : "soft light";

  themeToggleButton.textContent = isDark
    ? "Switch to soft light"
    : "Switch to terminal dark";
  themeToggleButton.setAttribute("aria-pressed", String(isDark));
  themeToggleButton.setAttribute("aria-label", `Current theme: ${currentThemeLabel}. Activate to switch to ${nextThemeLabel}.`);
  themeToggleButton.setAttribute("title", `Theme: ${currentThemeLabel}`);
}

function restoreTheme() {
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
  setTheme(savedTheme || document.documentElement.dataset.theme || "dark");
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

function renderListSection(title, items, emptyMessage = "") {
  if (!Array.isArray(items) || items.length === 0) {
    return emptyMessage
      ? `<section class="result-section"><h4>${escapeHtml(title)}</h4><p class="result-empty">${escapeHtml(emptyMessage)}</p></section>`
      : "";
  }

  const listItems = items
    .map((item) => `<li class="result-list__item"><span>${escapeHtml(item)}</span></li>`)
    .join("");

  return `
    <section class="result-section">
      <h4>${escapeHtml(title)}</h4>
      <ul class="result-list">${listItems}</ul>
    </section>
  `;
}

function renderPathSection(title, pathValue) {
  if (!pathValue) {
    return "";
  }

  return `
    <section class="result-section">
      <h4>${escapeHtml(title)}</h4>
      <pre class="result-path">${escapeHtml(pathValue)}</pre>
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
  summaryRows = [],
  sections = [],
} = {}) {
  const labelledBy = container.parentElement?.getAttribute("aria-labelledby");
  const headingText = labelledBy ? document.getElementById(labelledBy)?.textContent?.trim() : "";
  const panelLabel = container.dataset.resultTitle || headingText || "Command output";
  if (container.parentElement) {
    container.parentElement.dataset.panelLabel = `[${panelLabel}]`;
  }
  container.innerHTML = `
    <div class="result-card__header">
      <span class="result-badge result-badge--${escapeHtml(tone)}">${escapeHtml(badgeLabel)}</span>
      <p class="result-message">${escapeHtml(message)}</p>
    </div>
    ${renderSummaryRows(summaryRows)}
    <div class="result-sections">${sections.filter(Boolean).join("")}</div>
  `;
}

function renderScanSummary(result) {
  const imageCount = result.image_count ?? 0;
  const estimatedPages = result.estimated_pages ?? 0;
  const availableSubfolders = Array.isArray(result.available_subfolders)
    ? result.available_subfolders.map(normalizeSubfolderOption).filter(Boolean)
    : [];
  const sampleFiles = Array.isArray(result.sample_files) ? result.sample_files : [];
  const hasImages = imageCount > 0;

  renderResultCard(scanResultEl, {
    tone: result.valid ? "success" : "warning",
    badgeLabel: result.valid ? "Ready" : "Needs attention",
    message: result.message || (result.valid ? "Folder is ready." : "We couldn't use this folder yet."),
    summaryRows: [
      { label: "Images", value: pluralize(imageCount, "image") },
      { label: "Estimated pages", value: pluralize(estimatedPages, "page") },
      {
        label: "Folder options",
        value: availableSubfolders.length > 0 ? pluralize(availableSubfolders.length, "subfolder") : "None",
      },
    ],
    sections: [
      renderListSection(
        "Sample files",
        sampleFiles,
        hasImages ? "No sample files were returned for this scan." : "Add images to this folder to preview sample files.",
      ),
      renderListSection(
        "Available subfolders",
        availableSubfolders.map(({ displayName, fullPath }) =>
          displayName === fullPath ? displayName : `${displayName} (${fullPath})`,
        ),
      ),
    ],
  });
}

function renderBatchFolderOutcomeSection(results) {
  if (!Array.isArray(results) || results.length === 0) {
    return "";
  }

  const listItems = results
    .map((result) => {
      const folderName = result.folder_name || result.displayName || result.output_path || "Folder";
      const status = result.success ? "Success" : "Failed";
      const outputFiles = Array.isArray(result.output_files) ? result.output_files : [];
      const outputSummary = outputFiles.length > 0
        ? outputFiles.join(", ")
        : result.output_path || result.message || "No output details returned.";

      return `<li class="result-list__item"><span>${escapeHtml(folderName)} — ${escapeHtml(status)} — ${escapeHtml(outputSummary)}</span></li>`;
    })
    .join("");

  return `
    <section class="result-section">
      <h4>Per-folder outcomes</h4>
      <ul class="result-list">${listItems}</ul>
    </section>
  `;
}

function renderBatchCoverCollageSummary(result) {
  const bundleResults = Array.isArray(result.bundle_results) ? result.bundle_results : [];
  const successfulResults = bundleResults.filter((bundleResult) => bundleResult?.success);
  const failedResults = bundleResults.filter((bundleResult) => !bundleResult?.success);
  const outputFiles = successfulResults.flatMap((bundleResult) => Array.isArray(bundleResult.output_files) ? bundleResult.output_files : []);
  const totalCollageFilesWritten = outputFiles.length;
  const totalImages = successfulResults.reduce((sum, bundleResult) => sum + (bundleResult.total_images ?? 0), 0);
  const outputRootPath = result.created_output_root_path || "";

  renderResultCard(generationResultEl, {
    tone: failedResults.length === 0 ? "success" : successfulResults.length > 0 ? "warning" : "warning",
    badgeLabel: failedResults.length === 0 ? "Completed" : successfulResults.length > 0 ? "Partial" : "Needs attention",
    message: result.message || (failedResults.length === 0
      ? `Built batch cover collages for ${pluralize(successfulResults.length, "folder")}.`
      : `Built batch cover collages for ${successfulResults.length} of ${bundleResults.length} selected folders.`),
    summaryRows: [
      { label: "Selected folders processed", value: pluralize(result.processed_folders ?? bundleResults.length, "folder") },
      { label: "Folders successfully generated", value: pluralize(result.generated_folders ?? successfulResults.length, "folder") },
      { label: "Total collage files written", value: pluralize(totalCollageFilesWritten, "file") },
      { label: "Selected folders", value: result.selected_folders === null || result.selected_folders === undefined ? null : pluralize(result.selected_folders, "folder") },
      { label: "Detected folders", value: result.total_detected_folders === null || result.total_detected_folders === undefined ? null : pluralize(result.total_detected_folders, "folder") },
      { label: "Images", value: pluralize(totalImages, "image") },
    ],
    sections: [
      renderBatchFolderOutcomeSection(bundleResults),
      renderPathSection("Created output root", outputRootPath),
    ],
  });
}

function renderGenerationSummary(result) {
  if (Array.isArray(result.bundle_results)) {
    renderBatchCoverCollageSummary(result);
    return;
  }

  const outputFiles = Array.isArray(result.output_files) ? result.output_files : [];
  const pagesGenerated = result.pages_generated ?? 0;
  const totalImages = result.total_images ?? 0;
  const processedFolders = result.processed_folders ?? null;
  const selectedFolders = result.selected_folders ?? processedFolders;
  const totalDetectedFolders = result.total_detected_folders ?? null;
  const generatedFolders = result.generated_folders ?? null;
  const outputPath = result.output_path || result.created_output_root_path || "";
  const outputPathLabel = result.created_output_root_path ? "Created output root" : "Output path";
  const videoFilePath = result.video_file || "";
  const requestedPreviewVideo = Boolean(createPreviewVideoEl?.checked);

  let message = result.message || "Done.";
  if (selectedFolders !== null && generatedFolders !== null) {
    const detectedSummary = totalDetectedFolders === null ? "" : ` out of ${pluralize(totalDetectedFolders, "detected folder")}`;
    message = `${message} Processed ${pluralize(selectedFolders, generationState.mode === "batch" ? "selected batch folder" : "selected folder")}${detectedSummary}; ${pluralize(generatedFolders, generationState.mode === "batch" ? "batch folder" : "folder")} generated pages.`;
  }
  if (requestedPreviewVideo && pagesGenerated <= 0) {
    message = `${message} Preview video was requested, but no pages were generated, so a video could not be created.`;
  }

  renderResultCard(generationResultEl, {
    tone: pagesGenerated > 0 || outputFiles.length > 0 || outputPath ? "success" : "neutral",
    badgeLabel: pagesGenerated > 0 ? "Completed" : "Finished",
    message,
    summaryRows: [
      { label: "Pages", value: pluralize(pagesGenerated, "page") },
      { label: "Images", value: pluralize(totalImages, "image") },
      { label: "Detected folders", value: totalDetectedFolders === null ? null : pluralize(totalDetectedFolders, "folder") },
      { label: "Selected folders", value: selectedFolders === null ? null : pluralize(selectedFolders, "folder") },
      { label: "Generated folders", value: generatedFolders === null ? null : pluralize(generatedFolders, "folder") },
      {
        label: "Outputs",
        value: outputFiles.length > 0 ? pluralize(outputFiles.length, "file") : outputPath ? "Saved path available" : "None",
      },
      { label: "Preview video", value: videoFilePath ? "Created" : requestedPreviewVideo ? "Not created" : "Not requested" },
    ],
    sections: [
      renderListSection("Output files", outputFiles),
      renderPathSection("Preview video file", videoFilePath),
      renderPathSection(outputPathLabel, outputPath),
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
    renderPendingResult(scanResultEl, "Ready", generationState.mode === "batch"
      ? "Mode updated. Run a parent-folder scan to continue the batch workflow."
      : "Mode updated. Run a new scan for the selected folder to continue.");
    renderPendingResult(generationResultEl, "Waiting", "No output yet. Run a scan first, then completed files will appear here.");
    applyGenerationMode();
  });
});

themeToggleButton?.addEventListener("click", () => {
  const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  setTheme(nextTheme);
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
  renderPendingResult(scanResultEl, "Scanning", generationState.mode === "batch" ? "Scanning parent folder contents to discover folders for batch page and cover-collage generation..." : "Scanning folder contents...");

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
    generationState.selectedBatchFolders = selectedBatchFolders;
    showSubfolderPicker(result.available_subfolders, selectedSubfolder);
  } else {
    clearSelectedWorkingFolder();
    setAvailableSubfolders([]);
    setSelectedBatchFolders([]);
    hideSubfolderPicker({ preserveOptions: false });
  }

  return result;
}

scanButton?.addEventListener("click", async () => {
  await runExclusive(() => scanCurrentFolder({ preserveSubfolderPicker: true }));
});

async function validateSelectedBatchFolders() {
  if (generationState.mode !== "batch") {
    return [];
  }

  const selectedBatchFolders = getSelectedBatchFolderPaths();
  if (!generationState.batchParentScanComplete) {
    renderPendingResult(scanResultEl, "Needs discovery", "Run the parent-folder scan before validating selected batch folders.");
    return [];
  }

  if (selectedBatchFolders.length === 0) {
    setBatchValidationResults([]);
    recomputeStepFiveState();
    renderPendingResult(scanResultEl, "Needs selection", "Choose at least one detected child folder before running Scan selected folders.");
    return [];
  }

  renderPendingResult(scanResultEl, "Scanning", `Scanning ${selectedBatchFolders.length} selected ${selectedBatchFolders.length === 1 ? "batch folder" : "batch folders"}...`);

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
  const invalidResults = results.filter((result) => !result.valid);
  const totalImages = results.reduce((sum, result) => sum + (result.image_count ?? 0), 0);
  const totalEstimatedPages = results.reduce((sum, result) => sum + (result.estimated_pages ?? 0), 0);

  renderResultCard(scanResultEl, {
    tone: invalidResults.length === 0 ? "success" : "warning",
    badgeLabel: invalidResults.length === 0 ? "Validated" : "Needs attention",
    message: invalidResults.length === 0
      ? `Selected batch folders scanned successfully. Validated ${results.length} ${results.length === 1 ? "batch folder" : "batch folders"}. Batch page and cover-collage generation are ready.`
      : `${invalidResults.length} of ${results.length} selected ${results.length === 1 ? "batch folder needs" : "batch folders need"} attention before generation.`,
    summaryRows: [
      { label: "Selected batch folders", value: pluralize(results.length, "folder") },
      { label: "Validated batch folders", value: pluralize(generationState.validatedBatchFolders.length, "folder") },
      { label: "Images", value: pluralize(totalImages, "image") },
      { label: "Estimated pages", value: pluralize(totalEstimatedPages, "page") },
    ],
    sections: [
      renderListSection(
        "Validated folders",
        results.filter((result) => result.valid).map((result) => `${result.displayName} (${result.image_count ?? 0} images)`),
        "No selected batch folders validated successfully.",
      ),
      renderListSection(
        "Folders needing attention",
        invalidResults.map((result) => `${result.displayName}: ${result.message || "Not ready"}`),
      ),
    ],
  });

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
  setBatchValidationResults([]);
  syncBatchSelectionUI();
});

clearSubfolderSelectionButton?.addEventListener("click", () => {
  setSelectedBatchFolders([]);
  setBatchValidationResults([]);
  syncBatchSelectionUI();
});

useSubfolderButton?.addEventListener("click", async () => {
  if (!subfolderPickerEl.value) {
    return;
  }

  generationState.selectedWorkingFolder = subfolderPickerEl.value;
  renderPendingResult(scanResultEl, "Ready", `Selected subfolder: ${subfolderPickerEl.selectedOptions?.[0]?.textContent?.trim() || subfolderPickerEl.value}.`);
  setScanReadyState(generationState.singleFolderReady);
});

async function runCoverCollage() {
  const selectedTemplateLabel = readSelectedCoverCollageTemplateLabel();

  if (generationState.mode !== "batch") {
    renderPendingResult(generationResultEl, "Working", `Building ${selectedTemplateLabel} cover collage...`);

    const { ok, data: result, errorMessage } = await postJson("/api/jobs/generate-cover-collage", readCoverCollagePayload());
    if (!ok) {
      renderFailedResult(generationResultEl, errorMessage);
      return;
    }

    renderGenerationSummary(result);
    return;
  }

  const payload = buildBatchCoverCollagePayload();
  if (payload.selected_subfolders.length === 0 || !hasValidatedBatchSelection()) {
    renderPendingResult(generationResultEl, "Needs validation", "Select and validate one or more batch folders before running batch cover-collage generation.");
    return;
  }

  renderPendingResult(generationResultEl, "Working", `Running ${selectedTemplateLabel} batch cover-collage generation for ${payload.selected_subfolders.length} selected ${payload.selected_subfolders.length === 1 ? "batch folder" : "batch folders"}...`);

  const { ok, data: batchResult, errorMessage } = await postJson("/api/jobs/generate-cover-collage-batch", payload);
  if (!ok) {
    renderFailedResult(generationResultEl, errorMessage);
    return;
  }

  renderGenerationSummary(batchResult);
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
      renderPendingResult(generationResultEl, "Needs scan", "Run a parent-folder scan that finds at least one detected child folder before starting batch page or cover-collage generation.");
      updateBatchSelectionStatus();
      return;
    }

    if (selectedCount === 0) {
      renderPendingResult(generationResultEl, "Needs selection", "No batch folders selected. Choose at least one detected child folder before running Scan selected folders.");
      updateBatchSelectionStatus();
      return;
    }

    if (!generationState.batchValidationReady || !hasValidatedBatchSelection()) {
      renderPendingResult(generationResultEl, "Needs validation", "Run Scan selected folders successfully for the current batch selection before running batch page or cover-collage generation.");
      updateBatchSelectionStatus();
      return;
    }
  }

  await runExclusive(runPageGeneration);
});

async function runPageGeneration() {
  const config = getSelectedGenerationModeConfig();
  renderPendingResult(generationResultEl, "Working", getGenerationStatusMessage());

  const { ok, data: result, errorMessage } = await postJson(config.endpoint, config.payload());
  if (!ok) {
    renderFailedResult(generationResultEl, errorMessage);
    return;
  }

  renderGenerationSummary(result);
}

restoreTheme();
updatePreviewVideoControls();
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
