import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { createHash } from "node:crypto";
import { appendFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

const MIN_BOX_EDGE = 0.005;
const MAX_BOXES = 12;
const EKG_MAX_BOX_WIDTH = 0.35;
const EKG_MAX_BOX_HEIGHT = 0.3;
const EKG_MAX_BOX_AREA = 0.08;
const ECG_FOUNDER_TOOL = "ecg_founder_analyze_waveform";
const ECG_FOUNDER_MODEL_ID = "PKUDigitalHealth/ECGFounder";
const ECG_FOUNDER_MODEL_REVISION = "04edac702b61c91face519774ddcc0cd712fef23";
const ECG_FOUNDER_12_LEAD_CHECKPOINT_SHA256 =
  "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997";
const ECG_FOUNDER_SCHEMA_VERSION = 1;
const ECG_FOUNDER_DEFAULT_TIMEOUT_MS = 30_000;
const ECG_FOUNDER_MAX_TIMEOUT_MS = 30_000;
const ECG_FOUNDER_MAX_RESPONSE_CHARS = 1_000_000;
const ECG_FOUNDER_MAX_PREDICTIONS = 150;
const ECG_FOUNDER_NONCE_CACHE_LIMIT = 64;
const ECG_RHYTHM_METHOD = "lead_II_qrs_energy_v1";
const ECG_FOUNDER_ALLOWED_HOSTS = new Set([
  "127.0.0.1",
  "localhost",
  "[::1]",
  "::1",
]);

const ecgFounderParameters = {
  type: "object",
  additionalProperties: false,
  required: ["artifact_id", "lead_mode", "evidence_nonce"],
  properties: {
    artifact_id: {
      type: "string",
      minLength: 1,
      maxLength: 128,
      pattern: "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
      description:
        "Opaque waveform artifact identifier supplied by the trusted desktop app. Never invent one or pass a filesystem path.",
    },
    lead_mode: {
      type: "string",
      enum: ["12_lead"],
      description: "Checkpoint/input mode declared by the waveform artifact.",
    },
    evidence_nonce: {
      type: "string",
      pattern: "^[a-f0-9]{32}$",
      description:
        "Per-analysis correlation nonce supplied by the trusted app. Copy it exactly and never reuse or invent it.",
    },
    max_predictions: {
      type: "integer",
      minimum: 1,
      maximum: 20,
      default: 10,
      description: "Maximum ranked probability scores requested from the sidecar.",
    },
  },
};

const bboxParameters = {
  type: "object",
  additionalProperties: false,
  required: ["modality", "source_image_sha256", "evidence_nonce", "boxes"],
  properties: {
    modality: {
      type: "string",
      enum: ["EKG", "CXR", "CT_BRAIN", "auto"],
      description: "Modality of the attached full image.",
    },
    source_image_sha256: {
      type: "string",
      pattern: "^[a-f0-9]{64}$",
      description:
        "SHA-256 supplied by the trusted app for this exact attached image. Copy it verbatim.",
    },
    evidence_nonce: {
      type: "string",
      pattern: "^[a-f0-9]{32}$",
      description:
        "Per-turn nonce supplied by the trusted app. Copy it exactly; never invent or reuse it.",
    },
    boxes: {
      type: "array",
      maxItems: MAX_BOXES,
      description:
        "Candidate normalized boxes relative to the full attached image.",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["id", "x", "y", "w", "h"],
        properties: {
          id: { type: "string", minLength: 1, maxLength: 64 },
          x: { type: "number" },
          y: { type: "number" },
          w: { type: "number" },
          h: { type: "number" },
          reason: { type: "string", maxLength: 240 },
        },
      },
    },
  },
};

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function clip01(value) {
  return Math.min(1, Math.max(0, value));
}

function roundCoordinate(value) {
  return Math.round(value * 10000) / 10000;
}

function validateBox(raw, index, modality) {
  const id = String(raw?.id ?? `box-${index + 1}`).trim();
  const x = finiteNumber(raw?.x);
  const y = finiteNumber(raw?.y);
  const w = finiteNumber(raw?.w);
  const h = finiteNumber(raw?.h);
  if (!id || x === null || y === null || w === null || h === null) {
    return { accepted: false, id: id || `box-${index + 1}`, reason: "non_finite" };
  }
  if (w <= 0 || h <= 0) {
    return { accepted: false, id, reason: "non_positive_extent" };
  }

  const left = clip01(x);
  const top = clip01(y);
  const right = clip01(x + w);
  const bottom = clip01(y + h);
  const clippedWidth = right - left;
  const clippedHeight = bottom - top;
  if (clippedWidth < MIN_BOX_EDGE || clippedHeight < MIN_BOX_EDGE) {
    return { accepted: false, id, reason: "too_small_after_clipping" };
  }
  if (
    modality === "EKG" &&
    (clippedWidth > EKG_MAX_BOX_WIDTH ||
      clippedHeight > EKG_MAX_BOX_HEIGHT ||
      clippedWidth * clippedHeight > EKG_MAX_BOX_AREA)
  ) {
    return { accepted: false, id, reason: "ekg_box_too_broad" };
  }

  return {
    accepted: true,
    id,
    box: {
      x: roundCoordinate(left),
      y: roundCoordinate(top),
      w: roundCoordinate(clippedWidth),
      h: roundCoordinate(clippedHeight),
    },
    reason: String(raw?.reason ?? "").trim(),
    clipped: left !== x || top !== y || right !== x + w || bottom !== y + h,
  };
}

async function appendAuditRecord(toolCallId, details) {
  const path = String(process.env.DICOM_BBOX_AUDIT_PATH ?? "").trim();
  if (!path) return;
  const digest = createHash("sha256")
    .update(JSON.stringify(details))
    .digest("hex");
  const record = {
    schema_version: 2,
    recorded_at: new Date().toISOString(),
    tool: "dicom_bbox_validate",
    tool_call_id: String(toolCallId ?? ""),
    accepted_count: details.accepted.length,
    rejected_count: details.rejected.length,
    source_image_sha256: details.source_image_sha256,
    evidence_nonce: details.evidence_nonce,
    accepted_boxes_sha256: acceptedBoxesDigest(details.accepted),
    details_sha256: digest,
  };
  await mkdir(dirname(path), { recursive: true });
  await appendFile(path, `${JSON.stringify(record)}\n`, { encoding: "utf8" });
}

function acceptedBoxesDigest(accepted) {
  const canonical = accepted
    .map((item) => item.box)
    .filter(Boolean)
    .map((box) => [box.x, box.y, box.w, box.h].map((value) => Number(value).toFixed(4)))
    .sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)));
  return createHash("sha256").update(JSON.stringify(canonical)).digest("hex");
}

function resolveEcgFounderConfig(env = process.env) {
  const endpointText = String(env.DICOM_ECGFOUNDER_ENDPOINT ?? "").trim();
  const token = String(env.DICOM_ECGFOUNDER_TOKEN ?? "").trim();
  if (!endpointText || !token) return null;

  let endpoint;
  try {
    endpoint = new URL(endpointText);
  } catch {
    throw new Error("DICOM_ECGFOUNDER_ENDPOINT must be a valid loopback URL");
  }
  if (endpoint.protocol !== "http:") {
    throw new Error("ECGFounder sidecar must use loopback HTTP");
  }
  if (!ECG_FOUNDER_ALLOWED_HOSTS.has(endpoint.hostname.toLowerCase())) {
    throw new Error("ECGFounder sidecar endpoint must be loopback-only");
  }
  if (endpoint.username || endpoint.password) {
    throw new Error("ECGFounder sidecar credentials must not be embedded in the URL");
  }

  const timeoutValue = Number(env.DICOM_ECGFOUNDER_TIMEOUT_MS);
  const timeoutMs = Number.isFinite(timeoutValue)
    ? Math.min(ECG_FOUNDER_MAX_TIMEOUT_MS, Math.max(1_000, Math.trunc(timeoutValue)))
    : ECG_FOUNDER_DEFAULT_TIMEOUT_MS;
  const auditPath = String(env.DICOM_ECGFOUNDER_AUDIT_PATH ?? "").trim();
  return {
    endpoint: endpoint.toString(),
    token,
    timeoutMs,
    auditPath,
  };
}

function cleanText(value, maxLength = 300) {
  return String(value ?? "").trim().slice(0, maxLength);
}

function cleanStringList(value, maxItems = 24, maxLength = 160) {
  if (!Array.isArray(value)) return [];
  return value
    .slice(0, maxItems)
    .map((item) => cleanText(item, maxLength))
    .filter(Boolean);
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    const entries = Object.keys(value)
      .filter((key) => value[key] !== undefined)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`);
    return `{${entries.join(",")}}`;
  }
  return JSON.stringify(value);
}

function sanitizeRhythmMeasurement(raw) {
  const unavailable = {
    method: ECG_RHYTHM_METHOD,
    lead: "II",
    status: "unavailable",
    diagnostic_scope: "rhythm_regularity_only",
    reason: "not_provided",
    rr_interval_count: 0,
    limitations: [],
  };
  if (raw === undefined || raw === null) return unavailable;
  if (typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("ECG rhythm measurement must be an object");
  }
  const method = cleanText(raw.method, 64);
  const lead = cleanText(raw.lead, 8);
  const status = cleanText(raw.status, 32);
  const scope = cleanText(raw.diagnostic_scope, 64);
  if (
    method !== ECG_RHYTHM_METHOD ||
    lead !== "II" ||
    scope !== "rhythm_regularity_only" ||
    !new Set(["ok", "insufficient", "unavailable"]).has(status)
  ) {
    throw new Error("ECG rhythm measurement contract mismatch");
  }
  const limitations = cleanStringList(raw.limitations, 8, 200);
  const reason = cleanText(raw.reason, 80);
  const intervalCount = Number(raw.rr_interval_count ?? 0);
  if (!Number.isInteger(intervalCount) || intervalCount < 0 || intervalCount > 30) {
    throw new Error("ECG rhythm measurement has invalid interval count");
  }
  const common = {
    method,
    lead,
    status,
    diagnostic_scope: scope,
    reason,
    rr_interval_count: intervalCount,
    limitations,
  };
  if (status !== "ok") return common;

  const intervals = Array.isArray(raw.rr_intervals_ms)
    ? raw.rr_intervals_ms.map((value) => Number(value))
    : [];
  if (
    intervals.length !== intervalCount ||
    intervalCount < 5 ||
    intervals.some(
      (value) => !Number.isFinite(value) || value < 250 || value > 3000,
    )
  ) {
    throw new Error("ECG rhythm measurement has invalid R-R intervals");
  }
  const regularitySignal = cleanText(raw.regularity_signal, 32);
  if (!new Set(["regular", "irregular", "indeterminate"]).has(regularitySignal)) {
    throw new Error("ECG rhythm measurement has invalid regularity signal");
  }
  const metrics = {
    beat_count: Number(raw.beat_count),
    median_rr_ms: finiteNumber(raw.median_rr_ms),
    heart_rate_bpm_from_median_rr: finiteNumber(
      raw.heart_rate_bpm_from_median_rr,
    ),
    rr_cv: finiteNumber(raw.rr_cv),
    rr_rmssd_ms: finiteNumber(raw.rr_rmssd_ms),
    rr_range_ms: finiteNumber(raw.rr_range_ms),
    successive_rr_diff_over_80ms_fraction: finiteNumber(
      raw.successive_rr_diff_over_80ms_fraction,
    ),
  };
  if (
    !Number.isInteger(metrics.beat_count) ||
    metrics.beat_count !== intervalCount + 1 ||
    metrics.median_rr_ms === null ||
    metrics.median_rr_ms < 250 ||
    metrics.median_rr_ms > 3000 ||
    metrics.heart_rate_bpm_from_median_rr === null ||
    metrics.heart_rate_bpm_from_median_rr < 20 ||
    metrics.heart_rate_bpm_from_median_rr > 240 ||
    metrics.rr_cv === null ||
    metrics.rr_cv < 0 ||
    metrics.rr_cv > 2 ||
    metrics.rr_rmssd_ms === null ||
    metrics.rr_rmssd_ms < 0 ||
    metrics.rr_rmssd_ms > 3000 ||
    metrics.rr_range_ms === null ||
    metrics.rr_range_ms < 0 ||
    metrics.rr_range_ms > 3000 ||
    metrics.successive_rr_diff_over_80ms_fraction === null ||
    metrics.successive_rr_diff_over_80ms_fraction < 0 ||
    metrics.successive_rr_diff_over_80ms_fraction > 1
  ) {
    throw new Error("ECG rhythm measurement has invalid metrics");
  }
  return {
    ...common,
    ...metrics,
    rr_intervals_ms: intervals.map((value) => Math.round(value)),
    regularity_signal: regularitySignal,
    rule: {
      irregular_rr_cv_min: 0.1,
      irregular_successive_diff_fraction_min: 0.25,
    },
  };
}

function sanitizeEcgFounderResponse(raw, request) {
  if (request?.lead_mode !== "12_lead") {
    throw new Error("Only the pinned ECGFounder 12-lead contract is supported");
  }
  if (!/^[a-f0-9]{32}$/.test(String(request?.evidence_nonce ?? ""))) {
    throw new Error("ECGFounder evidence nonce does not match the tool contract");
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("ECGFounder sidecar returned a non-object response");
  }
  if (Number(raw.schema_version) !== ECG_FOUNDER_SCHEMA_VERSION) {
    throw new Error("Unsupported ECGFounder sidecar schema_version");
  }

  const status = cleanText(raw.status, 32);
  if (!new Set(["ok", "ineligible", "unavailable", "error"]).has(status)) {
    throw new Error("ECGFounder sidecar returned an invalid status");
  }
  const common = {
    schema_version: ECG_FOUNDER_SCHEMA_VERSION,
    status,
    evidence_type: "ecg_waveform_classification",
    artifact_id: request.artifact_id,
    lead_mode: request.lead_mode,
    evidence_nonce: request.evidence_nonce,
    use_policy: "supporting_evidence_only",
    spatial_localization: "not_provided",
    limitations: cleanStringList(raw.limitations),
  };
  if (status !== "ok") {
    return {
      ...common,
      reason: cleanText(raw.reason || "sidecar_not_ready"),
      predictions: [],
    };
  }

  const model = raw.model;
  const input = raw.input;
  const calibration = raw.calibration;
  if (!model || typeof model !== "object" || Array.isArray(model)) {
    throw new Error("ECGFounder response is missing model provenance");
  }
  if (cleanText(model.id, 128) !== ECG_FOUNDER_MODEL_ID) {
    throw new Error("ECGFounder response model id does not match the tool contract");
  }
  const revision = cleanText(model.revision, 128);
  const checkpointSha256 = cleanText(model.checkpoint_sha256, 64).toLowerCase();
  if (
    revision !== ECG_FOUNDER_MODEL_REVISION ||
    checkpointSha256 !== ECG_FOUNDER_12_LEAD_CHECKPOINT_SHA256
  ) {
    throw new Error("ECGFounder response does not match the pinned 12-lead model");
  }
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("ECGFounder response is missing input provenance");
  }
  const sourceKind = cleanText(input.source_kind, 64);
  if (!new Set(["raw_waveform", "validated_digitized_waveform"]).has(sourceKind)) {
    throw new Error("ECGFounder only accepts raw or validated digitized waveforms");
  }
  if (
    sourceKind === "validated_digitized_waveform" &&
    input.digitization_quality_status !== "validated"
  ) {
    throw new Error("Digitized waveform lacks a passed digitization quality gate");
  }
  if (
    Number(input.model_sample_rate_hz) !== 500 ||
    Number(input.model_duration_sec) !== 10 ||
    Number(input.model_points_per_lead) !== 5000
  ) {
    throw new Error("ECGFounder response does not prove the official 500 Hz/10 s input contract");
  }
  const sourceSha256 = cleanText(input.source_sha256, 64).toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(sourceSha256)) {
    throw new Error("ECGFounder response lacks waveform source provenance");
  }

  const leadNames = cleanStringList(input.lead_names, 12, 8);
  const expectedLeadCount = request.lead_mode === "12_lead" ? 12 : 1;
  if (leadNames.length !== expectedLeadCount) {
    throw new Error("ECGFounder response lead count does not match lead_mode");
  }

  if (!calibration || typeof calibration !== "object" || Array.isArray(calibration)) {
    throw new Error("ECGFounder response is missing calibration provenance");
  }
  const calibrationStatus = cleanText(calibration.status, 32);
  if (!new Set(["validated", "uncalibrated"]).has(calibrationStatus)) {
    throw new Error("ECGFounder calibration status must be validated or uncalibrated");
  }
  const preprocessingImplementation = cleanText(
    raw.preprocessing?.implementation,
    160,
  );
  const preprocessingRevision = cleanText(
    raw.preprocessing?.implementation_revision,
    128,
  );
  const preprocessingSteps = cleanStringList(raw.preprocessing?.steps, 16, 160);
  if (
    !preprocessingImplementation ||
    !preprocessingRevision ||
    preprocessingSteps.length === 0
  ) {
    throw new Error("ECGFounder response lacks pinned preprocessing provenance");
  }
  const calibrationDataset = cleanText(calibration.dataset, 160);
  const calibrationRevision = cleanText(calibration.revision, 128);
  if (
    calibrationStatus === "validated" &&
    (!calibrationDataset || !calibrationRevision)
  ) {
    throw new Error("Validated ECGFounder thresholds lack calibration provenance");
  }

  if (!Array.isArray(raw.predictions)) {
    throw new Error("ECGFounder response is missing predictions");
  }
  const predictionLimit = Math.min(
    ECG_FOUNDER_MAX_PREDICTIONS,
    Number(request.max_predictions ?? 10),
  );
  const predictions = raw.predictions.slice(0, predictionLimit).map((item) => {
    const label = cleanText(item?.label, 160);
    const probability = Number(item?.probability);
    if (!label || !Number.isFinite(probability) || probability < 0 || probability > 1) {
      throw new Error("ECGFounder response contains an invalid prediction");
    }
    const threshold = Number(item?.threshold);
    const hasThreshold =
      calibrationStatus === "validated" &&
      Number.isFinite(threshold) &&
      threshold >= 0 &&
      threshold <= 1;
    return {
      label,
      probability: Math.round(probability * 1_000_000) / 1_000_000,
      threshold: hasThreshold ? threshold : null,
      decision: hasThreshold
        ? probability >= threshold
          ? "positive"
          : "negative"
        : "uncalibrated_score",
    };
  });
  if (predictions.length === 0) {
    throw new Error("ECGFounder status=ok response contains no predictions");
  }

  return {
    ...common,
    model: {
      id: ECG_FOUNDER_MODEL_ID,
      revision,
      checkpoint_sha256: checkpointSha256,
    },
    input: {
      source_kind: sourceKind,
      source_sha256: sourceSha256,
      lead_names: leadNames,
      source_sample_rate_hz: finiteNumber(input.source_sample_rate_hz),
      model_sample_rate_hz: 500,
      model_duration_sec: 10,
      model_points_per_lead: 5000,
      digitization_quality_status:
        sourceKind === "validated_digitized_waveform" ? "validated" : "not_applicable",
    },
    preprocessing: {
      implementation: preprocessingImplementation,
      implementation_revision: preprocessingRevision,
      steps: preprocessingSteps,
    },
    calibration: {
      status: calibrationStatus,
      dataset: calibrationDataset,
      revision: calibrationRevision,
    },
    predictions,
    rhythm_measurement: sanitizeRhythmMeasurement(raw.rhythm_measurement),
  };
}

async function appendEcgFounderAuditRecord(
  toolCallId,
  details,
  config,
  { latencyMs = 0 } = {},
) {
  if (!config.auditPath) return;
  const artifactDigest = createHash("sha256")
    .update(details.artifact_id)
    .digest("hex");
  const { artifact_id: _artifactId, ...responseEvidenceWithoutDigest } = details;
  const responseEvidence = {
    ...responseEvidenceWithoutDigest,
    artifact_id_sha256: artifactDigest,
  };
  const record = {
    schema_version: 1,
    recorded_at: new Date().toISOString(),
    tool: ECG_FOUNDER_TOOL,
    tool_call_id: String(toolCallId ?? ""),
    evidence_nonce: details.evidence_nonce,
    status: details.status,
    artifact_id_sha256: artifactDigest,
    lead_mode: details.lead_mode ?? "",
    model_id: details.model?.id ?? "",
    model_revision: details.model?.revision ?? "",
    checkpoint_sha256: details.model?.checkpoint_sha256 ?? "",
    source_sha256: details.input?.source_sha256 ?? "",
    preprocessing_revision: details.preprocessing?.implementation_revision ?? "",
    calibration_status: details.calibration?.status ?? "",
    calibration_revision: details.calibration?.revision ?? "",
    prediction_count: details.predictions.length,
    predictions: details.predictions,
    rhythm_regularity_signal:
      details.rhythm_measurement?.regularity_signal ?? "",
    rr_interval_count: details.rhythm_measurement?.rr_interval_count ?? 0,
    response_evidence: responseEvidence,
    response_sha256: createHash("sha256")
      .update(canonicalJson(responseEvidence))
      .digest("hex"),
    latency_ms: Math.max(0, Math.trunc(Number(latencyMs) || 0)),
    failure_reason: details.reason ?? "",
  };
  await mkdir(dirname(config.auditPath), { recursive: true });
  await appendFile(config.auditPath, `${JSON.stringify(record)}\n`, {
    encoding: "utf8",
  });
}

async function appendEcgFounderDuplicateAuditRecord(
  toolCallId,
  request,
  cached,
  config,
) {
  if (!config.auditPath) return;
  const record = {
    schema_version: 1,
    recorded_at: new Date().toISOString(),
    tool: "ecg_founder_duplicate_suppressed",
    original_tool: ECG_FOUNDER_TOOL,
    tool_call_id: String(toolCallId ?? ""),
    original_tool_call_id: cached.toolCallId,
    evidence_nonce: request.evidence_nonce,
    status: "duplicate_suppressed",
    original_status: cached.details.status,
    artifact_id_sha256: createHash("sha256")
      .update(request.artifact_id)
      .digest("hex"),
    request_sha256: cached.requestSha256,
  };
  await mkdir(dirname(config.auditPath), { recursive: true });
  await appendFile(config.auditPath, `${JSON.stringify(record)}\n`, {
    encoding: "utf8",
  });
}

function compactEcgFounderToolResult(details, { duplicateSuppressed = false } = {}) {
  const rhythm = details.rhythm_measurement;
  const rhythmSummary =
    rhythm && typeof rhythm === "object"
      ? {
          method: rhythm.method,
          lead: rhythm.lead,
          status: rhythm.status,
          diagnostic_scope: rhythm.diagnostic_scope,
          beat_count: rhythm.beat_count,
          rr_interval_count: rhythm.rr_interval_count,
          median_rr_ms: rhythm.median_rr_ms,
          heart_rate_bpm_from_median_rr: rhythm.heart_rate_bpm_from_median_rr,
          rr_cv: rhythm.rr_cv,
          rr_rmssd_ms: rhythm.rr_rmssd_ms,
          rr_range_ms: rhythm.rr_range_ms,
          successive_rr_diff_over_80ms_fraction:
            rhythm.successive_rr_diff_over_80ms_fraction,
          regularity_signal: rhythm.regularity_signal,
          limitations: rhythm.limitations,
        }
      : null;
  return {
    schema_version: ECG_FOUNDER_SCHEMA_VERSION,
    status: details.status,
    evidence_type: details.evidence_type ?? "ecg_waveform_classification",
    lead_mode: details.lead_mode,
    evidence_nonce: details.evidence_nonce,
    use_policy: "supporting_evidence_only",
    spatial_localization: "not_provided",
    calibration_status: details.calibration?.status ?? "",
    predictions: (details.predictions ?? []).map((item) => ({
      label: item.label,
      probability: item.probability,
      threshold: item.threshold,
      decision: item.decision,
    })),
    rhythm_measurement: rhythmSummary,
    provenance: {
      model_id: details.model?.id ?? "",
      model_revision: details.model?.revision ?? "",
      checkpoint_sha256: details.model?.checkpoint_sha256 ?? "",
      source_sha256: details.input?.source_sha256 ?? "",
      preprocessing_revision:
        details.preprocessing?.implementation_revision ?? "",
    },
    limitations: [
      "Ranked waveform support only; uncalibrated scores are not diagnoses.",
      "R-R timing measures regularity only and cannot diagnose atrial fibrillation.",
      "No image localization is provided; ground every bbox in the image.",
    ],
    tool_call_policy: {
      completed_for_nonce: true,
      repeat_calls_forbidden: true,
      duplicate_suppressed: duplicateSuppressed,
      next_action: "Finish visual reconciliation and the structured image report.",
    },
    reason: details.reason ?? "",
  };
}

function createEcgFounderTool(config, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") {
    throw new Error("ECGFounder tool requires a fetch implementation");
  }
  const completedByNonce = new Map();

  function rememberCompleted(nonce, entry) {
    completedByNonce.delete(nonce);
    completedByNonce.set(nonce, entry);
    while (completedByNonce.size > ECG_FOUNDER_NONCE_CACHE_LIMIT) {
      completedByNonce.delete(completedByNonce.keys().next().value);
    }
  }

  return {
    name: ECG_FOUNDER_TOOL,
    label: "Analyze ECG Waveform",
    description:
      "Request supporting ECGFounder probability evidence once for a trusted raw-waveform artifact. Call only when the app explicitly supplies an ECG waveform artifact id. Never call for a screenshot alone, never invent an id, never repeat a completed nonce, and never use this tool to create image bounding boxes.",
    promptSnippet:
      "ECGFounder waveform evidence (only for an app-supplied waveform artifact id)",
    promptGuidelines: [
      "Treat ECGFounder output as supporting evidence, not a final diagnosis.",
      "Do not convert uncalibrated scores into positive or negative diagnoses.",
      "Use the deterministic lead-II R-R measurement only as rhythm-regularity evidence; it does not identify P waves or diagnose atrial fibrillation.",
      "ECGFounder provides no image localization; ground every bbox in the attached image and crop/refine evidence.",
      "Call exactly once per evidence nonce. After the result, do not call again; finish visual reconciliation and the structured report promptly.",
    ],
    parameters: ecgFounderParameters,
    executionMode: "sequential",
    async execute(toolCallId, args, signal) {
      const request = {
        schema_version: ECG_FOUNDER_SCHEMA_VERSION,
        artifact_id: String(args?.artifact_id ?? ""),
        lead_mode: String(args?.lead_mode ?? ""),
        evidence_nonce: String(args?.evidence_nonce ?? ""),
        max_predictions: Number(args?.max_predictions ?? 10),
      };
      if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(request.artifact_id)) {
        throw new Error("ECGFounder artifact id does not match the tool contract");
      }
      if (request.lead_mode !== "12_lead") {
        throw new Error("Only the pinned ECGFounder 12-lead contract is supported");
      }
      if (!/^[a-f0-9]{32}$/.test(request.evidence_nonce)) {
        throw new Error("ECGFounder evidence nonce does not match the tool contract");
      }
      const requestSha256 = createHash("sha256")
        .update(canonicalJson(request))
        .digest("hex");
      const cached = completedByNonce.get(request.evidence_nonce);
      if (cached) {
        if (cached.requestSha256 !== requestSha256) {
          throw new Error("ECGFounder evidence nonce was reused with different inputs");
        }
        await appendEcgFounderDuplicateAuditRecord(
          toolCallId,
          request,
          cached,
          config,
        );
        const summary = compactEcgFounderToolResult(cached.details, {
          duplicateSuppressed: true,
        });
        return {
          content: [{ type: "text", text: JSON.stringify(summary) }],
          details: summary,
        };
      }
      const controller = new AbortController();
      const startedAt = Date.now();
      const abortFromCaller = () => controller.abort(signal?.reason);
      signal?.addEventListener("abort", abortFromCaller, { once: true });
      const timer = setTimeout(() => controller.abort("sidecar_timeout"), config.timeoutMs);
      try {
        const response = await fetchImpl(config.endpoint, {
          method: "POST",
          redirect: "error",
          headers: {
            authorization: `Bearer ${config.token}`,
            "content-type": "application/json",
            accept: "application/json",
          },
          body: JSON.stringify(request),
          signal: controller.signal,
        });
        const contentLength = Number(response.headers?.get?.("content-length"));
        if (
          Number.isFinite(contentLength) &&
          contentLength > ECG_FOUNDER_MAX_RESPONSE_CHARS
        ) {
          throw new Error("ECGFounder sidecar response is too large");
        }
        const responseText = await response.text();
        if (responseText.length > ECG_FOUNDER_MAX_RESPONSE_CHARS) {
          throw new Error("ECGFounder sidecar response is too large");
        }
        if (!response.ok) {
          throw new Error(`ECGFounder sidecar HTTP ${response.status}`);
        }
        let raw;
        try {
          raw = JSON.parse(responseText);
        } catch {
          throw new Error("ECGFounder sidecar returned invalid JSON");
        }
        const details = sanitizeEcgFounderResponse(raw, request);
        await appendEcgFounderAuditRecord(toolCallId, details, config, {
          latencyMs: Date.now() - startedAt,
        });
        rememberCompleted(request.evidence_nonce, {
          requestSha256,
          toolCallId: String(toolCallId ?? ""),
          details,
        });
        const summary = compactEcgFounderToolResult(details);
        return {
          content: [{ type: "text", text: JSON.stringify(summary) }],
          details: summary,
        };
      } catch (error) {
        const failure = {
          status: "error",
          artifact_id: request.artifact_id,
          lead_mode: request.lead_mode,
          evidence_nonce: request.evidence_nonce,
          reason: cleanText(error?.message || "ecgfounder_tool_error", 240),
          predictions: [],
        };
        await appendEcgFounderAuditRecord(toolCallId, failure, config, {
          latencyMs: Date.now() - startedAt,
        });
        rememberCompleted(request.evidence_nonce, {
          requestSha256,
          toolCallId: String(toolCallId ?? ""),
          details: failure,
        });
        throw error;
      } finally {
        clearTimeout(timer);
        signal?.removeEventListener("abort", abortFromCaller);
      }
    },
  };
}

function createBboxValidationTool() {
  return {
    name: "dicom_bbox_validate",
    label: "Validate Medical Image Boxes",
    description:
      "Validate and clip normalized full-image bounding boxes before the medical-image result is finalized. Use the returned accepted boxes verbatim.",
    parameters: bboxParameters,
    async execute(_toolCallId, args) {
      const modality = String(args?.modality ?? "auto");
      const sourceImageSha256 = String(args?.source_image_sha256 ?? "");
      const evidenceNonce = String(args?.evidence_nonce ?? "");
      if (!/^[a-f0-9]{64}$/.test(sourceImageSha256)) {
        throw new Error("bbox source image SHA-256 does not match the tool contract");
      }
      if (!/^[a-f0-9]{32}$/.test(evidenceNonce)) {
        throw new Error("bbox evidence nonce does not match the tool contract");
      }
      const boxes = Array.isArray(args?.boxes) ? args.boxes : [];
      const checked = boxes
        .slice(0, MAX_BOXES)
        .map((box, index) => validateBox(box, index, modality));
      const accepted = checked
        .filter((item) => item.accepted)
        .map(({ id, box, reason, clipped }) => ({ id, box, reason, clipped }));
      const rejected = checked
        .filter((item) => !item.accepted)
        .map(({ id, reason }) => ({ id, reason }));
      const details = {
        modality,
        source_image_sha256: sourceImageSha256,
        evidence_nonce: evidenceNonce,
        coordinateSpace: "normalized_full_image",
        accepted,
        rejected,
      };
      await appendAuditRecord(_toolCallId, details);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(details),
          },
        ],
        details,
      };
    },
  };
}

export default definePluginEntry({
  id: "dicom-overlay-agent-harness",
  name: "DICOM Overlay Agent Harness",
  description:
    "OpenClaw runtime boundary for the desktop medical-image crop/refine harness.",
  register(api) {
    api.registerTool(createBboxValidationTool(), {
      name: "dicom_bbox_validate",
    });
    let ecgFounderConfig;
    try {
      ecgFounderConfig = resolveEcgFounderConfig();
    } catch (error) {
      api.logger.error(`ECGFounder tool disabled: ${error.message}`);
      return;
    }
    if (ecgFounderConfig) {
      api.registerTool(createEcgFounderTool(ecgFounderConfig), {
        name: ECG_FOUNDER_TOOL,
      });
    }
  },
});

export {
  acceptedBoxesDigest,
  createBboxValidationTool,
  createEcgFounderTool,
  resolveEcgFounderConfig,
  sanitizeEcgFounderResponse,
};
