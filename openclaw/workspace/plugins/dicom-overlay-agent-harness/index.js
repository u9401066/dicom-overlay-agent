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
const ECG_FOUNDER_DEFAULT_TIMEOUT_MS = 45_000;
const ECG_FOUNDER_MAX_RESPONSE_CHARS = 1_000_000;
const ECG_FOUNDER_MAX_PREDICTIONS = 150;
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
  required: ["modality", "boxes"],
  properties: {
    modality: {
      type: "string",
      enum: ["EKG", "CXR", "CT_BRAIN", "auto"],
      description: "Modality of the attached full image.",
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
    schema_version: 1,
    recorded_at: new Date().toISOString(),
    tool: "dicom_bbox_validate",
    tool_call_id: String(toolCallId ?? ""),
    accepted_count: details.accepted.length,
    rejected_count: details.rejected.length,
    details_sha256: digest,
  };
  await mkdir(dirname(path), { recursive: true });
  await appendFile(path, `${JSON.stringify(record)}\n`, { encoding: "utf8" });
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
    ? Math.min(120_000, Math.max(1_000, Math.trunc(timeoutValue)))
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

function createEcgFounderTool(config, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") {
    throw new Error("ECGFounder tool requires a fetch implementation");
  }
  return {
    name: ECG_FOUNDER_TOOL,
    label: "Analyze ECG Waveform",
    description:
      "Request supporting ECGFounder probability evidence for a trusted raw-waveform artifact. Call only when the app explicitly supplies an ECG waveform artifact id. Never call for a screenshot alone, never invent an id, and never use this tool to create image bounding boxes.",
    promptSnippet:
      "ECGFounder waveform evidence (only for an app-supplied waveform artifact id)",
    promptGuidelines: [
      "Treat ECGFounder output as supporting evidence, not a final diagnosis.",
      "Do not convert uncalibrated scores into positive or negative diagnoses.",
      "ECGFounder provides no image localization; ground every bbox in the attached image and crop/refine evidence.",
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
        return {
          content: [{ type: "text", text: JSON.stringify(details) }],
          details,
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
  createEcgFounderTool,
  resolveEcgFounderConfig,
  sanitizeEcgFounderResponse,
};
