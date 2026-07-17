"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const byId = (id) => document.getElementById(id);
const fileUrl = (path) => `/file/${encodeURIComponent(path)}`;
const CHECKS = [
  ["silhouette", "Readable silhouette"],
  ["scale", "Scale & proportions"],
  ["topology", "Topology integrity"],
  ["materials", "Materials & texel intent"],
  ["rigging", "Rig / deformation"],
  ["gameplay", "Gameplay readability"],
  ["performance", "Runtime budget"],
  ["provenance", "Provenance evidence"],
];
const CHECK_OPTIONS = [
  ["unchecked", "Unchecked"],
  ["pass", "Pass"],
  ["needs-work", "Needs work"],
  ["not-applicable", "N/A"],
];
const CATEGORIES = ["silhouette", "topology", "materials", "rigging", "scale", "performance", "gameplay", "pipeline", "other"];
const SEVERITIES = ["note", "minor", "major", "blocker"];
const NEURAL_CRITERIA_UI = [
  ["semanticIntent", "Semantic intent"],
  ["temporalCoherence", "Temporal coherence"],
  ["footContacts", "Foot contacts"],
  ["balance", "Balance / support"],
  ["deformation", "Deformation integrity"],
  ["weaponGrip", "Weapon / hand grip"],
  ["transitionContinuity", "Transition continuity"],
  ["physicalPlausibility", "Physical plausibility"],
];

const state = {
  catalog: [],
  filtered: [],
  active: null,
  compare: null,
  review: null,
  pendingPoint: null,
  stageFilter: "all",
  saveTimer: null,
  pinMode: false,
  renderer: null,
  authority: null,
  replayRun: null,
  activeReviewRun: null,
  motionLab: null,
  visualEvidence: {status: "not_captured", reason: null, invalidatedAt: null},
};

function setVisualEvidenceStatus(status, reason = null) {
  state.visualEvidence = {status, reason, invalidatedAt: new Date().toISOString()};
  document.documentElement.dataset.forgeLensEvidence = status;
  const blocked = status === "webgl_context_lost" || status === "viewer_unsupported";
  if (byId("captureButton")) byId("captureButton").disabled = blocked;
  if (byId("submitReportButton")) byId("submitReportButton").disabled = blocked || status === "recapture_required";
  if (byId("submitReportInline")) byId("submitReportInline").disabled = blocked || status === "recapture_required";
}

let viewerContextQueue = Promise.resolve();
function blobBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error("viewer capture could not be read"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.readAsDataURL(blob);
  });
}
function recordViewerContextEvent(event, captureBlob = null) {
  if (!state.activeReviewRun?.runId || !state.activeReviewRun.viewerContext?.headReceiptSha256) return Promise.resolve();
  viewerContextQueue = viewerContextQueue.catch(() => {}).then(async () => {
    const body = {
      runId: state.activeReviewRun.runId,
      event,
      expectedPreviousSha256: state.activeReviewRun.viewerContext.headReceiptSha256,
    };
    if (captureBlob) body.capturePngBase64 = await blobBase64(captureBlob);
    const response = await apiFetch("/api/viewer-context", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    const receipt = await response.json();
    if (!response.ok) throw new Error(receipt.error || `viewer-context HTTP ${response.status}`);
    const snapshotResponse = await apiFetch(`/api/review-run?runId=${encodeURIComponent(state.activeReviewRun.runId)}`);
    const snapshot = await snapshotResponse.json();
    if (!snapshotResponse.ok) throw new Error(snapshot.error || `ReviewRun refresh HTTP ${snapshotResponse.status}`);
    state.activeReviewRun = snapshot;
    renderReviewRunGate();
  });
  return viewerContextQueue;
}

class ViewerUnsupportedError extends Error {
  constructor(reasons) {
    super(`viewer_unsupported: ${reasons.join(", ")}`);
    this.name = "ViewerUnsupportedError";
    this.status = "viewer_unsupported";
    this.reasons = reasons;
  }
}

function inspectViewerEligibility(document) {
  const reasons = [];
  if ((document.accessors || []).some(accessor => accessor?.sparse)) reasons.push("sparse_accessor");
  if ((document.meshes || []).some(mesh => (mesh.primitives || []).some(primitive => (primitive.targets || []).length))) reasons.push("morph_target");
  for (const mesh of document.meshes || []) {
    for (const primitive of mesh.primitives || []) {
      if ((primitive.mode ?? 4) !== 4) reasons.push(`unsupported_primitive_mode:${primitive.mode}`);
    }
  }
  for (const animation of document.animations || []) {
    if ((animation.samplers || []).some(sampler => (sampler.interpolation || "LINEAR") === "CUBICSPLINE")) reasons.push("cubic_spline_animation");
    if ((animation.channels || []).some(channel => channel.target?.path === "weights")) reasons.push("morph_weight_animation");
  }
  for (const extension of document.extensionsRequired || []) reasons.push(`unsupported_required_extension:${extension}`);
  if ((document.images || []).some(image => typeof image.uri === "string" && !image.uri.startsWith("data:"))) reasons.push("external_image_uri");
  return {status: reasons.length ? "viewer_unsupported" : "viewer_supported", reasons: [...new Set(reasons)].sort()};
}

async function apiFetch(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!['GET', 'HEAD'].includes(method)) {
    if (!state.authority?.csrfToken) throw new Error("Authenticated browser authority is unavailable");
    headers.set("X-ForgeLens-CSRF", state.authority.csrfToken);
  }
  return fetch(url, {...options, method, headers, credentials: "same-origin"});
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "—";
  const units = ["B", "KiB", "MiB", "GiB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value >= 100 || unit === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
}

function formatNumber(value) {
  return Number.isFinite(value) ? new Intl.NumberFormat("en-US").format(value) : "—";
}

function toast(message, error = false) {
  const node = byId("toast");
  node.textContent = message;
  node.classList.toggle("is-error", error);
  node.classList.add("is-visible");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("is-visible"), 2400);
}

function setSaveState(message, kind = "") {
  const node = byId("saveState");
  node.textContent = message;
  node.className = `save-state${kind ? ` is-${kind}` : ""}`;
}

// ---------------------------------------------------------------------------
// Minimal column-major matrix/vector math — deliberately local, no wrappers.
// ---------------------------------------------------------------------------

const m4Identity = () => new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]);

function m4Multiply(a, b) {
  const out = new Float32Array(16);
  for (let column = 0; column < 4; column += 1) {
    for (let row = 0; row < 4; row += 1) {
      out[column * 4 + row] =
        a[0 * 4 + row] * b[column * 4 + 0] +
        a[1 * 4 + row] * b[column * 4 + 1] +
        a[2 * 4 + row] * b[column * 4 + 2] +
        a[3 * 4 + row] * b[column * 4 + 3];
    }
  }
  return out;
}

function m4Perspective(fovy, aspect, near, far) {
  const f = 1 / Math.tan(fovy / 2);
  const nf = 1 / (near - far);
  return new Float32Array([f/aspect,0,0,0, 0,f,0,0, 0,0,(far+near)*nf,-1, 0,0,2*far*near*nf,0]);
}

function v3Sub(a, b) { return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]; }
function v3Add(a, b) { return [a[0]+b[0], a[1]+b[1], a[2]+b[2]]; }
function v3Scale(a, value) { return [a[0]*value, a[1]*value, a[2]*value]; }
function v3Dot(a, b) { return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]; }
function v3Cross(a, b) { return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]; }
function v3Length(a) { return Math.hypot(a[0], a[1], a[2]); }
function v3Normalize(a) { const length = v3Length(a) || 1; return v3Scale(a, 1/length); }

function m4LookAt(eye, center, up) {
  const z = v3Normalize(v3Sub(eye, center));
  const x = v3Normalize(v3Cross(up, z));
  const y = v3Cross(z, x);
  return new Float32Array([
    x[0], y[0], z[0], 0,
    x[1], y[1], z[1], 0,
    x[2], y[2], z[2], 0,
    -v3Dot(x, eye), -v3Dot(y, eye), -v3Dot(z, eye), 1,
  ]);
}

function m4Invert(a) {
  const out = new Float32Array(16);
  const b00=a[0]*a[5]-a[1]*a[4], b01=a[0]*a[6]-a[2]*a[4], b02=a[0]*a[7]-a[3]*a[4];
  const b03=a[1]*a[6]-a[2]*a[5], b04=a[1]*a[7]-a[3]*a[5], b05=a[2]*a[7]-a[3]*a[6];
  const b06=a[8]*a[13]-a[9]*a[12], b07=a[8]*a[14]-a[10]*a[12], b08=a[8]*a[15]-a[11]*a[12];
  const b09=a[9]*a[14]-a[10]*a[13], b10=a[9]*a[15]-a[11]*a[13], b11=a[10]*a[15]-a[11]*a[14];
  let det=b00*b11-b01*b10+b02*b09+b03*b08-b04*b07+b05*b06;
  if (!det) return null;
  det=1/det;
  out[0]=(a[5]*b11-a[6]*b10+a[7]*b09)*det; out[1]=(-a[1]*b11+a[2]*b10-a[3]*b09)*det;
  out[2]=(a[13]*b05-a[14]*b04+a[15]*b03)*det; out[3]=(-a[9]*b05+a[10]*b04-a[11]*b03)*det;
  out[4]=(-a[4]*b11+a[6]*b08-a[7]*b07)*det; out[5]=(a[0]*b11-a[2]*b08+a[3]*b07)*det;
  out[6]=(-a[12]*b05+a[14]*b02-a[15]*b01)*det; out[7]=(a[8]*b05-a[10]*b02+a[11]*b01)*det;
  out[8]=(a[4]*b10-a[5]*b08+a[7]*b06)*det; out[9]=(-a[0]*b10+a[1]*b08-a[3]*b06)*det;
  out[10]=(a[12]*b04-a[13]*b02+a[15]*b00)*det; out[11]=(-a[8]*b04+a[9]*b02-a[11]*b00)*det;
  out[12]=(-a[4]*b09+a[5]*b07-a[6]*b06)*det; out[13]=(a[0]*b09-a[1]*b07+a[2]*b06)*det;
  out[14]=(-a[12]*b03+a[13]*b01-a[14]*b00)*det; out[15]=(a[8]*b03-a[9]*b01+a[10]*b00)*det;
  return out;
}

function transformPoint(matrix, point, divide = false) {
  const x=point[0], y=point[1], z=point[2], w=point.length > 3 ? point[3] : 1;
  const result = [
    matrix[0]*x+matrix[4]*y+matrix[8]*z+matrix[12]*w,
    matrix[1]*x+matrix[5]*y+matrix[9]*z+matrix[13]*w,
    matrix[2]*x+matrix[6]*y+matrix[10]*z+matrix[14]*w,
    matrix[3]*x+matrix[7]*y+matrix[11]*z+matrix[15]*w,
  ];
  if (divide && result[3]) return [result[0]/result[3], result[1]/result[3], result[2]/result[3]];
  return result;
}

function composeNode(node) {
  if (Array.isArray(node.matrix) && node.matrix.length === 16) return new Float32Array(node.matrix);
  const translation = node.translation || [0,0,0];
  const rotation = node.rotation || [0,0,0,1];
  const scale = node.scale || [1,1,1];
  const [x,y,z,w] = rotation;
  const x2=x+x, y2=y+y, z2=z+z;
  const xx=x*x2, xy=x*y2, xz=x*z2, yy=y*y2, yz=y*z2, zz=z*z2, wx=w*x2, wy=w*y2, wz=w*z2;
  return new Float32Array([
    (1-(yy+zz))*scale[0], (xy+wz)*scale[0], (xz-wy)*scale[0], 0,
    (xy-wz)*scale[1], (1-(xx+zz))*scale[1], (yz+wx)*scale[1], 0,
    (xz+wy)*scale[2], (yz-wx)*scale[2], (1-(xx+yy))*scale[2], 0,
    translation[0], translation[1], translation[2], 1,
  ]);
}

function v4Normalize(value) {
  const length = Math.hypot(...value) || 1;
  return value.map(component => component / length);
}

function quaternionSlerp(a, b, amount) {
  let cosine = a[0]*b[0] + a[1]*b[1] + a[2]*b[2] + a[3]*b[3];
  let target = b;
  if (cosine < 0) { cosine = -cosine; target = b.map(value => -value); }
  if (cosine > .9995) return v4Normalize(a.map((value, index) => value + (target[index] - value) * amount));
  const angle = Math.acos(Math.max(-1, Math.min(1, cosine)));
  const sine = Math.sin(angle);
  const left = Math.sin((1 - amount) * angle) / sine;
  const right = Math.sin(amount * angle) / sine;
  return a.map((value, index) => value * left + target[index] * right);
}

// ---------------------------------------------------------------------------
// GLB 2.0 parsing and WebGL2 rendering.
// ---------------------------------------------------------------------------

const COMPONENTS = {5120:1, 5121:1, 5122:2, 5123:2, 5125:4, 5126:4};
const TYPE_WIDTH = {SCALAR:1, VEC2:2, VEC3:3, VEC4:4, MAT2:4, MAT3:9, MAT4:16};

function componentRead(view, offset, type) {
  if (type === 5120) return view.getInt8(offset);
  if (type === 5121) return view.getUint8(offset);
  if (type === 5122) return view.getInt16(offset, true);
  if (type === 5123) return view.getUint16(offset, true);
  if (type === 5125) return view.getUint32(offset, true);
  if (type === 5126) return view.getFloat32(offset, true);
  throw new Error(`Unsupported component type ${type}`);
}

function normalizedComponent(value, type) {
  if (type === 5120) return Math.max(value / 127, -1);
  if (type === 5121) return value / 255;
  if (type === 5122) return Math.max(value / 32767, -1);
  if (type === 5123) return value / 65535;
  if (type === 5125) return value / 4294967295;
  return value;
}

async function parseGlb(arrayBuffer, sourceUrl = "") {
  const header = new DataView(arrayBuffer, 0, 12);
  if (header.getUint32(0, true) !== 0x46546c67 || header.getUint32(4, true) !== 2) throw new Error("Only GLB 2.0 files are supported");
  if (header.getUint32(8, true) !== arrayBuffer.byteLength) throw new Error("GLB declared length mismatch");
  let offset = 12;
  let document = null;
  let binary = null;
  while (offset + 8 <= arrayBuffer.byteLength) {
    const chunkHeader = new DataView(arrayBuffer, offset, 8);
    const length = chunkHeader.getUint32(0, true);
    const type = chunkHeader.getUint32(4, true);
    offset += 8;
    if (offset + length > arrayBuffer.byteLength) throw new Error("Truncated GLB chunk");
    if (type === 0x4e4f534a) {
      const text = new TextDecoder().decode(new Uint8Array(arrayBuffer, offset, length)).replace(/[\u0000\s]+$/g, "");
      document = JSON.parse(text);
    } else if (type === 0x004e4942) {
      binary = arrayBuffer.slice(offset, offset + length);
    }
    offset += length;
  }
  if (!document || !binary) throw new Error("GLB requires JSON and BIN chunks");
  const eligibility = inspectViewerEligibility(document);
  if (eligibility.status === "viewer_unsupported") throw new ViewerUnsupportedError(eligibility.reasons);

  const accessor = (index, forceFloat = false) => {
    const spec = document.accessors?.[index];
    if (!spec || spec.sparse) throw new Error(`Accessor ${index} is missing or sparse`);
    const bufferView = document.bufferViews?.[spec.bufferView];
    if (!bufferView || (bufferView.buffer ?? 0) !== 0) throw new Error(`Accessor ${index} uses an unsupported buffer`);
    const components = TYPE_WIDTH[spec.type];
    const componentBytes = COMPONENTS[spec.componentType];
    if (!components || !componentBytes) throw new Error(`Accessor ${index} has an unsupported layout`);
    const stride = bufferView.byteStride || components * componentBytes;
    const start = (bufferView.byteOffset || 0) + (spec.byteOffset || 0);
    const view = new DataView(binary);
    const output = forceFloat || spec.componentType === 5126 ? new Float32Array(spec.count * components) : new Uint32Array(spec.count * components);
    for (let item = 0; item < spec.count; item += 1) {
      for (let part = 0; part < components; part += 1) {
        let value = componentRead(view, start + item * stride + part * componentBytes, spec.componentType);
        if (spec.normalized) value = normalizedComponent(value, spec.componentType);
        output[item * components + part] = value;
      }
    }
    return {array: output, count: spec.count, components, min: spec.min, max: spec.max};
  };

  const nodeWorlds = new Array(document.nodes?.length || 0);
  const nodeParents = new Array(document.nodes?.length || 0).fill(-1);
  for (let index = 0; index < (document.nodes?.length || 0); index += 1) {
    for (const child of document.nodes[index].children || []) nodeParents[child] = index;
  }
  const visitNode = (index, parent) => {
    const node = document.nodes[index];
    const world = m4Multiply(parent, composeNode(node));
    nodeWorlds[index] = world;
    for (const child of node.children || []) visitNode(child, world);
  };
  const scene = document.scenes?.[document.scene || 0] || {nodes: []};
  for (const root of scene.nodes || []) visitNode(root, m4Identity());

  const primitives = [];
  let lower = [Infinity, Infinity, Infinity];
  let upper = [-Infinity, -Infinity, -Infinity];
  for (let nodeIndex = 0; nodeIndex < (document.nodes?.length || 0); nodeIndex += 1) {
    const node = document.nodes[nodeIndex];
    if (!Number.isInteger(node.mesh)) continue;
    const modelMatrix = nodeWorlds[nodeIndex] || composeNode(node);
    const mesh = document.meshes?.[node.mesh];
    for (const raw of mesh?.primitives || []) {
      if ((raw.mode ?? 4) !== 4 || raw.attributes?.POSITION === undefined) continue;
      const positions = accessor(raw.attributes.POSITION, true).array;
      let normals = raw.attributes.NORMAL === undefined ? null : accessor(raw.attributes.NORMAL, true).array;
      const uvs = raw.attributes.TEXCOORD_0 === undefined ? new Float32Array((positions.length / 3) * 2) : accessor(raw.attributes.TEXCOORD_0, true).array;
      const joints = raw.attributes.JOINTS_0 === undefined ? new Float32Array((positions.length / 3) * 4) : accessor(raw.attributes.JOINTS_0, true).array;
      const weights = raw.attributes.WEIGHTS_0 === undefined ? new Float32Array((positions.length / 3) * 4) : accessor(raw.attributes.WEIGHTS_0, true).array;
      const indices = raw.indices === undefined ? Uint32Array.from({length: positions.length / 3}, (_, i) => i) : accessor(raw.indices, false).array;
      if (!normals) {
        normals = new Float32Array(positions.length);
        for (let i = 0; i + 2 < indices.length; i += 3) {
          const ai=indices[i]*3, bi=indices[i+1]*3, ci=indices[i+2]*3;
          const a=[positions[ai],positions[ai+1],positions[ai+2]], b=[positions[bi],positions[bi+1],positions[bi+2]], c=[positions[ci],positions[ci+1],positions[ci+2]];
          const normal=v3Normalize(v3Cross(v3Sub(b,a),v3Sub(c,a)));
          for (const vertex of [ai,bi,ci]) { normals[vertex]+=normal[0]; normals[vertex+1]+=normal[1]; normals[vertex+2]+=normal[2]; }
        }
      }
      for (let i = 0; i < positions.length; i += 3) {
        const world = transformPoint(modelMatrix, [positions[i], positions[i+1], positions[i+2]]);
        for (let axis=0; axis<3; axis+=1) { lower[axis]=Math.min(lower[axis],world[axis]); upper[axis]=Math.max(upper[axis],world[axis]); }
      }
      const edges = new Uint32Array(indices.length * 2);
      let edgeOffset = 0;
      for (let i=0; i+2<indices.length; i+=3) {
        const a=indices[i], b=indices[i+1], c=indices[i+2];
        edges.set([a,b,b,c,c,a], edgeOffset); edgeOffset += 6;
      }
      primitives.push({positions, normals, uvs, joints, weights, indices, edges, modelMatrix, nodeIndex, skin: node.skin ?? -1, material: raw.material ?? -1});
    }
  }
  if (!primitives.length || !Number.isFinite(lower[0])) throw new Error("No triangle mesh primitives found in GLB");

  const images = [];
  for (const image of document.images || []) {
    if (Number.isInteger(image.bufferView)) {
      const view = document.bufferViews[image.bufferView];
      const bytes = new Uint8Array(binary, view.byteOffset || 0, view.byteLength);
      images.push({blob: new Blob([bytes], {type: image.mimeType || "application/octet-stream"})});
    } else if (typeof image.uri === "string" && image.uri.startsWith("data:")) {
      images.push({uri: image.uri});
    } else {
      images.push({uri: image.uri && sourceUrl ? new URL(image.uri, sourceUrl).href : null});
    }
  }
  const baseNodes = (document.nodes || []).map(node => ({
    matrix: Array.isArray(node.matrix) ? node.matrix.slice() : null,
    translation: (node.translation || [0,0,0]).slice(),
    rotation: (node.rotation || [0,0,0,1]).slice(),
    scale: (node.scale || [1,1,1]).slice(),
  }));
  const skins = (document.skins || []).map(skin => {
    const raw = skin.inverseBindMatrices === undefined ? null : accessor(skin.inverseBindMatrices, true).array;
    const inverseBind = skin.joints.map((_, index) => raw ? new Float32Array(raw.slice(index*16, index*16+16)) : m4Identity());
    return {joints: skin.joints.slice(), inverseBind};
  });
  const animations = (document.animations || []).map((animation, index) => {
    const samplers = (animation.samplers || []).map(sampler => ({
      input: accessor(sampler.input, true).array,
      output: accessor(sampler.output, true).array,
      interpolation: sampler.interpolation || "LINEAR",
    }));
    const duration = samplers.reduce((maximum, sampler) => Math.max(maximum, sampler.input.at(-1) || 0), 0);
    return {name: animation.name || `Animation ${index+1}`, channels: animation.channels || [], samplers, duration};
  });
  return {document, binary, primitives, images, lower, upper, nodeWorlds, nodeParents, baseNodes, skins, animations, animationTime: 0, activeAnimation: 0};
}

class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl2", {antialias: true, alpha: false, preserveDrawingBuffer: true});
    if (!this.gl) throw new Error("WebGL2 is required");
    this.contextLost = false;
    this.bindContextEvents();
    this.primary = null; this.comparison = null; this.viewMode = "material"; this.grid = true;
    this.animationPlaying=false; this.animationLoop=true; this.animationSpeed=1;
    this.target=[0,0,0]; this.distance=3; this.yaw=.65; this.pitch=.25; this.radius=1;
    this.goalTarget=[0,0,0]; this.goalDistance=3; this.goalYaw=.65; this.goalPitch=.25; this.lastFrameTime=performance.now();
    this.drag=null; this.view=m4Identity(); this.projection=m4Identity(); this.viewProjection=m4Identity();
    this.program=this.createProgram(); this.gridProgram=this.createGridProgram(); this.whiteTexture=this.createWhiteTexture();
    this.bindEvents(); this.resizeObserver=new ResizeObserver(()=>this.resize()); this.resizeObserver.observe(canvas);
    requestAnimationFrame(()=>this.frame());
  }

  bindContextEvents() {
    this.canvas.addEventListener("webglcontextlost", event => {
      event.preventDefault();
      this.contextLost = true;
      this.animationPlaying = false;
      setVisualEvidenceStatus("webgl_context_lost", "WebGL context loss invalidated current visual evidence and benchmark state");
      recordViewerContextEvent("context_lost").catch(error => toast(error.message, true));
      document.documentElement.dataset.forgeLensModel = "context-lost";
      toast("WebGL context lost. Current visual evidence is invalid.", true);
    });
    this.canvas.addEventListener("webglcontextrestored", () => {
      this.contextLost = false;
      this.primary = null;
      this.comparison = null;
      this.gridBuffer = null;
      this.program = this.createProgram();
      this.gridProgram = this.createGridProgram();
      this.whiteTexture = this.createWhiteTexture();
      setVisualEvidenceStatus("recapture_required", "webgl_context_restored");
      recordViewerContextEvent("context_restored").catch(error => toast(error.message, true));
      document.documentElement.dataset.forgeLensModel = "context-restored-reload-required";
      toast("WebGL restored. Reload and recapture are required before submission.", true);
      if (state.active && !state.active.local) loadModel(state.active).catch(error => {
        console.error(error);
        toast(`Context restore reload failed: ${error.message}`, true);
      });
    });
  }

  shader(type, source) {
    const gl=this.gl, shader=gl.createShader(type); gl.shaderSource(shader,source); gl.compileShader(shader);
    if (!gl.getShaderParameter(shader,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || "Shader compile failed");
    return shader;
  }
  link(vertex, fragment) {
    const gl=this.gl, program=gl.createProgram(); gl.attachShader(program,this.shader(gl.VERTEX_SHADER,vertex)); gl.attachShader(program,this.shader(gl.FRAGMENT_SHADER,fragment)); gl.linkProgram(program);
    if (!gl.getProgramParameter(program,gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || "Shader link failed");
    return program;
  }
  createProgram() {
    return this.link(`#version 300 es
      layout(location=0) in vec3 aPosition; layout(location=1) in vec3 aNormal; layout(location=2) in vec2 aUv;
      uniform mat4 uViewProjection; uniform mat4 uModel;
      out vec3 vNormal; out vec2 vUv; out vec3 vWorld;
      void main(){ vec4 world=uModel*vec4(aPosition,1.0); vWorld=world.xyz; vNormal=mat3(uModel)*aNormal; vUv=aUv; gl_Position=uViewProjection*world; }
    `, `#version 300 es
      precision highp float; in vec3 vNormal; in vec2 vUv; in vec3 vWorld;
      uniform sampler2D uTexture; uniform bool uHasTexture; uniform int uMode; uniform vec4 uBaseColor; uniform vec3 uEye;
      out vec4 outColor;
      void main(){
        vec3 n=normalize(vNormal); vec3 color=uBaseColor.rgb;
        if(uHasTexture && uMode==0) color*=texture(uTexture,vUv).rgb;
        if(uMode==1) color=vec3(.58,.6,.59);
        if(uMode==2) color=n*.5+.5;
        if(uMode==4) { outColor=vec4(.24,.78,.76,.34); return; }
        vec3 light=normalize(vec3(.5,.85,.35)); float diffuse=max(dot(n,light),0.0);
        float rim=pow(1.0-max(dot(n,normalize(uEye-vWorld)),0.0),3.0);
        color*=.24+.76*diffuse; color+=vec3(.12)*rim;
        outColor=vec4(color,uBaseColor.a);
      }
    `);
  }
  createGridProgram() {
    return this.link(`#version 300 es
      layout(location=0) in vec3 aPosition; uniform mat4 uViewProjection; void main(){gl_Position=uViewProjection*vec4(aPosition,1.0);}
    `, `#version 300 es
      precision mediump float; out vec4 outColor; void main(){outColor=vec4(.48,.51,.53,.20);}
    `);
  }
  createWhiteTexture() {
    const gl=this.gl, texture=gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D,texture);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([255,255,255,255]));
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    return texture;
  }

  bindEvents() {
    this.canvas.addEventListener("pointerdown", event => {
      if (state.pinMode) return;
      this.canvas.setPointerCapture(event.pointerId);
      this.drag={x:event.clientX,y:event.clientY,yaw:this.goalYaw,pitch:this.goalPitch,target:[...this.goalTarget],pan:event.shiftKey||event.button===1};
    });
    this.canvas.addEventListener("pointermove", event => {
      if(!this.drag) return;
      const dx=event.clientX-this.drag.x, dy=event.clientY-this.drag.y;
      if(this.drag.pan) {
        const forward=v3Normalize(v3Sub(this.target,this.eye())); const right=v3Normalize(v3Cross(forward,[0,1,0])); const up=v3Cross(right,forward);
        const scale=this.distance/Math.max(this.canvas.clientHeight,1)*1.6;
        this.goalTarget=v3Add(this.drag.target,v3Add(v3Scale(right,-dx*scale),v3Scale(up,dy*scale)));
      } else {
        this.goalYaw=this.drag.yaw-dx*.006; this.goalPitch=Math.max(-1.45,Math.min(1.45,this.drag.pitch-dy*.006));
      }
    });
    const end=()=>{this.drag=null;}; this.canvas.addEventListener("pointerup",end); this.canvas.addEventListener("pointercancel",end);
    this.canvas.addEventListener("wheel", event=>{event.preventDefault(); this.goalDistance=Math.max(this.radius*.08,Math.min(this.radius*80,this.goalDistance*Math.exp(event.deltaY*.00085)));},{passive:false});
    this.canvas.addEventListener("click", event=>{if(state.pinMode) handlePinClick(event);});
  }
  eye() {
    const cp=Math.cos(this.pitch); return [this.target[0]+this.distance*cp*Math.sin(this.yaw),this.target[1]+this.distance*Math.sin(this.pitch),this.target[2]+this.distance*cp*Math.cos(this.yaw)];
  }
  cameraSnapshot() { return {target:[...this.target],distance:this.distance,yaw:this.yaw,pitch:this.pitch}; }
  applyCamera(camera) { if(!camera) return; this.goalTarget=[...camera.target]; this.goalDistance=camera.distance; this.goalYaw=camera.yaw; this.goalPitch=camera.pitch; }
  resize() {
    const ratio=Math.min(devicePixelRatio||1,2); const width=Math.max(1,Math.floor(this.canvas.clientWidth*ratio)), height=Math.max(1,Math.floor(this.canvas.clientHeight*ratio));
    if(this.canvas.width!==width||this.canvas.height!==height){this.canvas.width=width;this.canvas.height=height;}
  }
  frameModel(model=this.primary, immediate=false) {
    if(!model)return; this.radius=model.radius; this.goalTarget=model.center.slice(); this.goalDistance=Math.max(model.radius*6,.01); this.goalYaw=.65; this.goalPitch=.28;
    if(immediate){this.target=[...this.goalTarget];this.distance=this.goalDistance;this.yaw=this.goalYaw;this.pitch=this.goalPitch;}
  }
  async upload(parsed) {
    const gl=this.gl;
    for(const primitive of parsed.primitives) {
      primitive.vao=gl.createVertexArray(); gl.bindVertexArray(primitive.vao);
      const upload=(location,array,size)=>{const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,array,gl.STATIC_DRAW);gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,size,gl.FLOAT,false,0,0);return buffer;};
      primitive.positionBuffer=upload(0,primitive.positions,3); primitive.normalBuffer=upload(1,primitive.normals,3); primitive.uvBuffer=upload(2,primitive.uvs,2);
      primitive.indexBuffer=gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,primitive.indexBuffer); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,primitive.indices,gl.STATIC_DRAW);
      primitive.edgeBuffer=gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,primitive.edgeBuffer); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,primitive.edges,gl.STATIC_DRAW);
    }
    parsed.textures=[];
    for(const image of parsed.images) {
      try {
        const blob=image.blob || await fetch(image.uri).then(response=>response.blob()); const bitmap=await createImageBitmap(blob);
        const texture=gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D,texture); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);
        while(gl.getError()!==gl.NO_ERROR){}
        gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,bitmap); gl.generateMipmap(gl.TEXTURE_2D);
        gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);const textureError=gl.getError();bitmap.close();if(textureError!==gl.NO_ERROR)throw new Error(`WebGL texture upload failed (${textureError})`);parsed.textures.push(texture);
      } catch {
        throw new ViewerUnsupportedError([`texture_decode_failure:${parsed.textures.length}`]);
      }
    }
    parsed.center=parsed.lower.map((value,index)=>(value+parsed.upper[index])/2);
    parsed.radius=Math.max(v3Length(v3Sub(parsed.upper,parsed.lower))/2,.001);
    return parsed;
  }
  materialFor(model,index) {
    const source=model.document.materials?.[index]?.pbrMetallicRoughness || {};
    const factor=source.baseColorFactor || [.72,.72,.7,1];
    const textureIndex=source.baseColorTexture?.index; const imageIndex=Number.isInteger(textureIndex)?model.document.textures?.[textureIndex]?.source:null;
    return {factor,texture:Number.isInteger(imageIndex)?model.textures[imageIndex]:null};
  }
  setAnimationTime(value) {
    if(!this.primary?.animations?.length)return;
    const clip=this.primary.animations[this.primary.activeAnimation];
    this.primary.animationTime=Math.max(0,Math.min(clip.duration,value));
    this.updateAnimation(this.primary); updateAnimationUi();
  }
  setAnimationClip(index) {
    if(!this.primary?.animations?.[index])return;
    this.primary.activeAnimation=index; this.primary.animationTime=0;
    this.updateAnimation(this.primary); updateAnimationUi();
  }
  updateAnimation(model) {
    const clip=model.animations?.[model.activeAnimation]; if(!clip)return;
    const nodes=model.baseNodes.map(node=>({matrix:node.matrix,translation:node.translation.slice(),rotation:node.rotation.slice(),scale:node.scale.slice()}));
    for(const channel of clip.channels){
      const sampler=clip.samplers[channel.sampler],target=nodes[channel.target?.node]; if(!sampler||!target)continue;
      const times=sampler.input,time=model.animationTime; let right=times.findIndex(value=>value>=time); if(right<0)right=times.length-1;
      const left=Math.max(0,right-1),span=times[right]-times[left],amount=span>0?(time-times[left])/span:0,path=channel.target.path,width=path==="rotation"?4:path==="weights"?0:3;
      if(!width)continue;
      const a=Array.from(sampler.output.slice(left*width,left*width+width)),b=Array.from(sampler.output.slice(right*width,right*width+width));
      const value=sampler.interpolation==="STEP"?a:path==="rotation"?quaternionSlerp(a,b,amount):a.map((component,index)=>component+(b[index]-component)*amount);
      if(path==="translation")target.translation=value; if(path==="rotation")target.rotation=value; if(path==="scale")target.scale=value; target.matrix=null;
    }
    const worlds=new Array(nodes.length);
    const visit=(index,parent)=>{const world=m4Multiply(parent,composeNode(nodes[index]));worlds[index]=world;for(const child of model.document.nodes[index].children||[])visit(child,world);};
    const scene=model.document.scenes?.[model.document.scene||0]||{nodes:[]}; for(const root of scene.nodes||[])visit(root,m4Identity()); model.nodeWorlds=worlds;
    const animatedLower=[Infinity,Infinity,Infinity],animatedUpper=[-Infinity,-Infinity,-Infinity];
    for(const primitive of model.primitives){
      primitive.modelMatrix=worlds[primitive.nodeIndex]||m4Identity(); primitive.jointMatrices=null;
      if(primitive.skin<0)continue; const skin=model.skins[primitive.skin]; if(!skin||skin.joints.length>64)continue;
      const inverseMesh=m4Invert(primitive.modelMatrix); if(!inverseMesh)continue;
      primitive.jointMatrices=skin.joints.map((joint,index)=>m4Multiply(m4Multiply(inverseMesh,worlds[joint]||m4Identity()),skin.inverseBind[index]));
      const skinnedPositions=new Float32Array(primitive.positions.length),skinnedNormals=new Float32Array(primitive.normals.length);
      for(let vertex=0;vertex<primitive.positions.length/3;vertex+=1){const px=primitive.positions[vertex*3],py=primitive.positions[vertex*3+1],pz=primitive.positions[vertex*3+2],nx=primitive.normals[vertex*3],ny=primitive.normals[vertex*3+1],nz=primitive.normals[vertex*3+2];let ox=0,oy=0,oz=0,onx=0,ony=0,onz=0;
        for(let influence=0;influence<4;influence+=1){const weight=primitive.weights[vertex*4+influence];if(!weight)continue;const matrix=primitive.jointMatrices[primitive.joints[vertex*4+influence]];if(!matrix)continue;ox+=weight*(matrix[0]*px+matrix[4]*py+matrix[8]*pz+matrix[12]);oy+=weight*(matrix[1]*px+matrix[5]*py+matrix[9]*pz+matrix[13]);oz+=weight*(matrix[2]*px+matrix[6]*py+matrix[10]*pz+matrix[14]);onx+=weight*(matrix[0]*nx+matrix[4]*ny+matrix[8]*nz);ony+=weight*(matrix[1]*nx+matrix[5]*ny+matrix[9]*nz);onz+=weight*(matrix[2]*nx+matrix[6]*ny+matrix[10]*nz);}
        const normalLength=Math.hypot(onx,ony,onz)||1;skinnedPositions.set([ox,oy,oz],vertex*3);skinnedNormals.set([onx/normalLength,ony/normalLength,onz/normalLength],vertex*3);const world=transformPoint(primitive.modelMatrix,[ox,oy,oz]);for(let axis=0;axis<3;axis+=1){animatedLower[axis]=Math.min(animatedLower[axis],world[axis]);animatedUpper[axis]=Math.max(animatedUpper[axis],world[axis]);}}
      const gl=this.gl;gl.bindBuffer(gl.ARRAY_BUFFER,primitive.positionBuffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,skinnedPositions);gl.bindBuffer(gl.ARRAY_BUFFER,primitive.normalBuffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,skinnedNormals);
    }
    if(Number.isFinite(animatedLower[0])){model.lower=animatedLower;model.upper=animatedUpper;model.center=animatedLower.map((value,index)=>(value+animatedUpper[index])/2);model.radius=Math.max(v3Length(animatedUpper.map((value,index)=>(value-animatedLower[index])/2)),.001);}
  }
  drawModel(model,comparison=false) {
    if(!model)return; const gl=this.gl; gl.useProgram(this.program);
    gl.uniformMatrix4fv(gl.getUniformLocation(this.program,"uViewProjection"),false,this.viewProjection);
    gl.uniform3fv(gl.getUniformLocation(this.program,"uEye"),this.eye()); gl.uniform1i(gl.getUniformLocation(this.program,"uTexture"),0);
    const mode=comparison?4:({material:0,clay:1,normals:2,wireframe:1}[this.viewMode]??0);
    gl.uniform1i(gl.getUniformLocation(this.program,"uMode"),mode);

    if(comparison){gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);}
    for(const primitive of model.primitives) {
      const material=this.materialFor(model,primitive.material); gl.uniformMatrix4fv(gl.getUniformLocation(this.program,"uModel"),false,primitive.modelMatrix);

      gl.uniform4fv(gl.getUniformLocation(this.program,"uBaseColor"),material.factor); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D,material.texture||this.whiteTexture);
      gl.uniform1i(gl.getUniformLocation(this.program,"uHasTexture"),Boolean(material.texture)); gl.bindVertexArray(primitive.vao);
      for(const [location,buffer,size] of [[0,primitive.positionBuffer,3],[1,primitive.normalBuffer,3],[2,primitive.uvBuffer,2]]){gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,size,gl.FLOAT,false,0,0);}
      if(this.viewMode==="wireframe"&&!comparison){gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,primitive.edgeBuffer);gl.drawElements(gl.LINES,primitive.edges.length,gl.UNSIGNED_INT,0);}
      else{gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,primitive.indexBuffer);gl.drawElements(gl.TRIANGLES,primitive.indices.length,gl.UNSIGNED_INT,0);}
    }
    if(comparison){gl.depthMask(true);gl.disable(gl.BLEND);}
  }
  drawGrid() {
    if(!this.grid||!this.primary)return; const gl=this.gl; const half=this.radius*2.5, step=Math.pow(10,Math.floor(Math.log10(this.radius)))/2, y=this.primary.lower[1]; const lines=[];
    for(let value=-half;value<=half+step*.5;value+=step){lines.push(-half,y,value, half,y,value, value,y,-half, value,y,half);}
    if(!this.gridBuffer)this.gridBuffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,this.gridBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(lines),gl.DYNAMIC_DRAW);
    gl.useProgram(this.gridProgram);gl.uniformMatrix4fv(gl.getUniformLocation(this.gridProgram,"uViewProjection"),false,this.viewProjection);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,0,0);gl.drawArrays(gl.LINES,0,lines.length/3);
  }
  renderSnapshot() {if(this.contextLost)throw new Error("webgl_context_lost");this.resize();const gl=this.gl;gl.viewport(0,0,this.canvas.width,this.canvas.height);gl.enable(gl.DEPTH_TEST);gl.clearColor(.035,.047,.057,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);const aspect=this.canvas.width/this.canvas.height;this.projection=m4Perspective(Math.PI/4,aspect,Math.max(this.radius*.001,.001),Math.max(this.radius*200,100));this.view=m4LookAt(this.eye(),this.target,[0,1,0]);this.viewProjection=m4Multiply(this.projection,this.view);this.drawGrid();this.drawModel(this.primary);this.drawModel(this.comparison,true);renderPins();}
  frame() {
    if(this.contextLost){requestAnimationFrame(()=>this.frame());return;}
    const now=performance.now(),dt=Math.min((now-this.lastFrameTime)/1000,.05),blend=1-Math.exp(-dt*14);this.lastFrameTime=now;
    if(this.primary?.animations?.length&&this.animationPlaying){const clip=this.primary.animations[this.primary.activeAnimation];let next=this.primary.animationTime+dt*this.animationSpeed;if(next>clip.duration){if(this.animationLoop)next=clip.duration?next%clip.duration:0;else{next=clip.duration;this.animationPlaying=false;}}this.primary.animationTime=next;this.updateAnimation(this.primary);updateAnimationUi();}
    this.yaw+=(this.goalYaw-this.yaw)*blend;this.pitch+=(this.goalPitch-this.pitch)*blend;this.distance+=(this.goalDistance-this.distance)*blend;
    for(let axis=0;axis<3;axis+=1)this.target[axis]+=(this.goalTarget[axis]-this.target[axis])*blend;
    this.resize(); const gl=this.gl; gl.viewport(0,0,this.canvas.width,this.canvas.height);gl.enable(gl.DEPTH_TEST);gl.clearColor(.035,.047,.057,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    const eye=this.eye();this.view=m4LookAt(eye,this.target,[0,1,0]);this.projection=m4Perspective(Math.PI/4,this.canvas.width/this.canvas.height,Math.max(this.radius*.001,.0001),Math.max(this.radius*200,100));this.viewProjection=m4Multiply(this.projection,this.view);
    this.drawGrid();this.drawModel(this.primary,false);this.drawModel(this.comparison,true);renderPins();requestAnimationFrame(()=>this.frame());
  }
  rayFromEvent(event) {
    const rect=this.canvas.getBoundingClientRect(); const x=((event.clientX-rect.left)/rect.width)*2-1, y=1-((event.clientY-rect.top)/rect.height)*2;
    const inverse=m4Invert(this.viewProjection); if(!inverse)return null;
    const near=transformPoint(inverse,[x,y,-1,1],true), far=transformPoint(inverse,[x,y,1,1],true); return {origin:near,direction:v3Normalize(v3Sub(far,near))};
  }
  pick(event) {
    if(!this.primary)return null; const ray=this.rayFromEvent(event);if(!ray)return null;let nearest=null;
    for(const primitive of this.primary.primitives){const p=primitive.positions, idx=primitive.indices, matrix=primitive.modelMatrix;
      for(let i=0;i+2<idx.length;i+=3){const a=transformPoint(matrix,[p[idx[i]*3],p[idx[i]*3+1],p[idx[i]*3+2]]),b=transformPoint(matrix,[p[idx[i+1]*3],p[idx[i+1]*3+1],p[idx[i+1]*3+2]]),c=transformPoint(matrix,[p[idx[i+2]*3],p[idx[i+2]*3+1],p[idx[i+2]*3+2]]);const hit=rayTriangle(ray.origin,ray.direction,a,b,c);if(hit&&(!nearest||hit.distance<nearest.distance))nearest=hit;}
    } return nearest;
  }
  project(point) { const clip=transformPoint(this.viewProjection,[...point,1]);if(clip[3]<=0)return null;const x=(clip[0]/clip[3]*.5+.5)*this.canvas.clientWidth,y=(1-(clip[1]/clip[3]*.5+.5))*this.canvas.clientHeight;return {x,y,visible:clip[2]/clip[3]>=-1&&clip[2]/clip[3]<=1}; }
}

function rayTriangle(origin,direction,a,b,c){const edge1=v3Sub(b,a),edge2=v3Sub(c,a),h=v3Cross(direction,edge2),det=v3Dot(edge1,h);if(Math.abs(det)<1e-8)return null;const inv=1/det,s=v3Sub(origin,a),u=inv*v3Dot(s,h);if(u<0||u>1)return null;const q=v3Cross(s,edge1),v=inv*v3Dot(direction,q);if(v<0||u+v>1)return null;const distance=inv*v3Dot(edge2,q);if(distance<=1e-6)return null;return {distance,world:v3Add(origin,v3Scale(direction,distance)),normal:v3Normalize(v3Cross(edge1,edge2))};}

async function loadModel(record, comparison=false, localBuffer=null) {
  byId("loadingState").hidden=false;
  try {
    const declaredEligibility = record.metrics?.viewerEligibility;
    if (declaredEligibility?.status === "viewer_unsupported") {
      document.documentElement.dataset.forgeLensViewer = "viewer_unsupported";
      setVisualEvidenceStatus("viewer_unsupported", (declaredEligibility.reasons || []).join(","));
      throw new ViewerUnsupportedError(declaredEligibility.reasons || ["catalog_declared_unsupported"]);
    }
    const url=localBuffer?"":fileUrl(record.path);const buffer=localBuffer||await fetch(url).then(response=>{if(!response.ok)throw new Error(`HTTP ${response.status}`);return response.arrayBuffer();});
    const parsed=await parseGlb(buffer,url);const model=await state.renderer.upload(parsed);
    if(comparison){state.renderer.comparison=model;state.compare=record;}else{state.renderer.primary=model;state.renderer.comparison=null;if(model.animations.length)state.renderer.updateAnimation(model);state.renderer.frameModel(model,true);setupAnimationForModel(model);}
    byId("viewportEmpty").hidden=true;
    document.documentElement.dataset.forgeLensViewer="viewer_supported";
    document.documentElement.dataset.forgeLensModel=`${model.primitives.length}:${model.animations.length}:${model.skins.length}`;
    if(state.visualEvidence.status==="not_captured")setVisualEvidenceStatus("ready_for_capture");
    return model;
  } catch(error) {
    if(error instanceof ViewerUnsupportedError){document.documentElement.dataset.forgeLensViewer="viewer_unsupported";setVisualEvidenceStatus("viewer_unsupported",error.reasons.join(","));}
    throw error;
  } finally {byId("loadingState").hidden=true;}
}

// ---------------------------------------------------------------------------
// Product interaction and persistent review state.
// ---------------------------------------------------------------------------

function renderLibrary() {
  const query=byId("assetSearch").value.trim().toLowerCase();
  const matches=state.catalog.filter(record=>{
    const text=`${record.family} ${record.stage} ${record.path}`.toLowerCase();
    return text.includes(query)&&(state.stageFilter==="all"||record.stage.toLowerCase().includes(state.stageFilter.toLowerCase()));
  });
  state.filtered=matches;byId("assetCount").textContent=String(matches.length);const list=byId("assetList");list.replaceChildren();
  const groups=new Map();
  for(const record of matches){if(!groups.has(record.family))groups.set(record.family,[]);groups.get(record.family).push(record);}
  for(const [family,records] of groups){const section=element("section","asset-family");const heading=element("div","asset-family-heading");heading.append(element("span",null,family.replaceAll("_"," ")),element("span",null,String(records.length)));section.append(heading);
    for(const record of records){const row=element("div","asset-row");row.tabIndex=0;row.dataset.id=record.id;row.classList.toggle("is-active",state.active?.id===record.id);row.classList.toggle("is-compare",state.compare?.id===record.id);row.setAttribute("role","option");row.setAttribute("aria-selected",String(state.active?.id===record.id));
      const icon=element("span","asset-stage-icon",stageAbbreviation(record.stage));const copy=element("span","asset-row-copy");copy.append(element("strong",null,record.stage),element("span",null,`${formatNumber(record.metrics?.triangles)} tris · ${formatBytes(record.metrics?.bytes)}`));
      const compare=element("button","asset-compare-action","Compare");compare.type="button";compare.addEventListener("click",event=>{event.stopPropagation();selectComparison(record);});row.append(icon,copy,compare);row.addEventListener("click",()=>selectAsset(record));row.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();selectAsset(record);}});section.append(row);
    } list.append(section);
  }
  if(!matches.length)list.append(element("div","library-empty","No indexed GLB assets match this filter."));
}

function stageAbbreviation(stage){if(stage.startsWith("Generated"))return"GEN";if(stage.startsWith("DCC"))return"DCC";if(stage.startsWith("Runtime"))return"RUN";if(stage.startsWith("Reference"))return"REF";return"SRC";}

function renderPipeline() {
  const container=byId("pipelineStages");container.replaceChildren();if(!state.active){byId("pipelineFamily").textContent="No family selected";return;}
  const records=state.catalog.filter(record=>record.family===state.active.family);byId("pipelineFamily").textContent=state.active.family.replaceAll("_"," ");
  records.forEach((record,index)=>{const stage=element("button","pipeline-stage");stage.type="button";stage.classList.toggle("is-active",record.id===state.active.id);const number=element("span","pipeline-stage-index",String(index+1));const copy=element("span","pipeline-stage-copy");copy.append(element("strong",null,record.stage),element("span",null,`${formatNumber(record.metrics?.triangles)} tris · ${formatBytes(record.metrics?.bytes)}`));stage.append(number,copy);stage.addEventListener("click",()=>selectAsset(record));container.append(stage);});
}

async function selectAsset(record) {
  if(state.active?.id===record.id)return;state.active=record;state.compare=null;state.renderer.comparison=null;renderLibrary();renderPipeline();renderAssetMetadata();renderEvidence();
  byId("familyCrumb").textContent=record.family.replaceAll("_"," ");byId("assetCrumb").textContent=record.stage;byId("activeSlot").textContent=record.stage;byId("compareSlotText").textContent="Choose another version";byId("compareToggle").disabled=true;byId("comparisonDelta").textContent="Select “Compare” on a library item";
  history.replaceState(null,"",`?asset=${encodeURIComponent(record.path)}`);setSaveState("Loading review…");
  try {await loadModel(record);const response=await apiFetch(`/api/review?asset=${encodeURIComponent(record.path)}`);if(!response.ok)throw new Error(`Review HTTP ${response.status}`);state.review=await response.json();setSaveState(state.review.updatedAt?"Review loaded":"Unsaved review",state.review.updatedAt?"saved":"");renderReview();}
  catch(error){console.error(error);setSaveState("Load failed","error");toast(error.message,true);}
}

async function selectComparison(record) {
  if(!state.active){await selectAsset(record);return;}if(record.id===state.active.id){toast("Choose a different asset or version for comparison",true);return;}
  try{await loadModel(record,true);byId("compareSlotText").textContent=`${record.family} · ${record.stage}`;byId("compareToggle").disabled=false;byId("compareToggle").classList.add("is-active");byId("comparisonDelta").textContent=metricDelta(state.active,record);renderLibrary();toast("Comparison overlay loaded in cyan");}catch(error){console.error(error);toast(`Comparison failed: ${error.message}`,true);}
}

function metricDelta(a,b){const ta=a.metrics?.triangles||0,tb=b.metrics?.triangles||0,ba=a.metrics?.bytes||0,bb=b.metrics?.bytes||0;const signed=value=>`${value>=0?"+":""}${formatNumber(value)}`;return `Δ triangles ${signed(tb-ta)} · Δ size ${signed(Math.round((bb-ba)/1024))} KiB`;}

function renderAssetMetadata(){const metrics=byId("metricsList"),identity=byId("identityList");metrics.replaceChildren();identity.replaceChildren();if(!state.active)return;const m=state.active.metrics||{},viewer=m.viewerEligibility||{status:"unknown",reasons:[]};for(const [label,value] of [["Triangles",formatNumber(m.triangles)],["Vertices",formatNumber(m.vertices)],["Meshes",formatNumber(m.meshes)],["Primitives",formatNumber(m.primitives)],["Materials",formatNumber(m.materials)],["Textures",formatNumber(m.textures)],["Animations",formatNumber(m.animations)],["Skins",formatNumber(m.skins)],["File size",formatBytes(m.bytes)]])appendMetric(metrics,label,value);for(const [label,value] of [["Family",state.active.family],["Stage",state.active.stage],["Path",state.active.path],["Generator",m.generator||"unknown"],["Extensions",(m.extensions||[]).join(", ")||"none"],["Viewer",viewer.status],["Viewer blockers",(viewer.reasons||[]).join(", ")||"none"],["Modified",state.active.modifiedAt]])appendMetric(identity,label,value);}
function appendMetric(list,label,value){const row=element("div");row.append(element("dt",null,label),element("dd",null,String(value)));list.append(row);}

function renderReviewRunGate(){
  const section=byId("reviewRunGate"),snapshot=state.activeReviewRun;
  section.hidden=!snapshot;
  if(!snapshot)return;
  byId("reviewRunState").textContent=snapshot.state;
  byId("reviewRunState").classList.toggle("is-submitted",["pass","fail"].includes(snapshot.state));
  const run=snapshot.reviewRun,lineage=run.lineage,eligibility=snapshot.eligibility||{};
  const metrics=byId("reviewRunMetrics");metrics.replaceChildren();
  for(const [label,value] of [
    ["Run",run.runId],
    ["State",snapshot.state],
    ["Decision head",snapshot.headReceiptSha256],
    ["Revision",lineage.code.revision],
    ["Workflow",lineage.workflowRevision],
    ["Truth",lineage.truthHash],
    ["Plan",lineage.canonicalPlanPacket.sha256],
    ["Evidence manifest",lineage.evidenceManifest.sha256],
    ["Geometry",lineage.geometryIdentitySha256],
    ["Pins",snapshot.pins?.length||0],
    ["Stale pins",(snapshot.pinStatuses||[]).filter(pin=>pin.status==="stale").length],
    ["Viewer context",`${snapshot.viewerContext?.status||"missing"} · generation ${snapshot.viewerContext?.generation??"?"}`],
  ])appendMetric(metrics,label,value);
  const eligible=Boolean(eligibility.eligibleForPass);
  const status=byId("reviewRunEligibility");
  status.textContent=eligible
    ? "PASS-ELIGIBLE · final external human decision still required"
    : "BLOCKED · admission packet is not pass-eligible";
  status.classList.toggle("is-eligible",eligible);
  const blockers=[...new Set([...(eligibility.blockers||[]),...(eligibility.passBlockers||[])])];
  const list=byId("reviewRunBlockers");list.replaceChildren();
  for(const blocker of blockers)list.append(element("li",null,blocker.replaceAll("_"," ")));
  if(!blockers.length)list.append(element("li",null,"No mechanical blocker. Final authority remains an external human operational attestation, not cryptographic proof."));
  const terminal=snapshot.state==="submitted", supersedable=["awaiting_evidence","awaiting_human","submitted"].includes(snapshot.state);
  const reason=byId("reviewRunTransitionReason"),reasonLabel=byId("reviewRunTransitionReasonLabel"),actions=byId("reviewRunTransitionActions"),transitionStatus=byId("reviewRunTransitionStatus");
  actions.hidden=!terminal&&!supersedable;reason.hidden=!terminal&&!supersedable;reasonLabel.hidden=!terminal&&!supersedable;
  byId("reviewRunFail").disabled=!terminal;byId("reviewRunSupersede").disabled=!supersedable;
  transitionStatus.textContent=terminal
    ? "Fail is available to this authenticated browser session. Pass remains import-only and requires a tracked-clean external human decision."
    : supersedable
      ? "Supersede is available to retire this immutable run before it reaches a terminal decision."
      : "This ReviewRun is terminal. Its append-only decision chain cannot be edited or extended.";
}

async function transitionActiveReviewRun(targetState){
  const snapshot=state.activeReviewRun,reason=byId("reviewRunTransitionReason").value.trim();
  if(!snapshot)return;
  if(!reason){toast("A terminal transition reason is required",true);byId("reviewRunTransitionReason").focus();return;}
  const buttons=[byId("reviewRunFail"),byId("reviewRunSupersede")];buttons.forEach(button=>{button.disabled=true;});
  try{
    const response=await apiFetch("/api/review-run-transition",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({runId:snapshot.runId,targetState,expectedPreviousSha256:snapshot.headReceiptSha256,details:{reason}})});
    const receipt=await response.json();if(!response.ok)throw new Error(receipt.error||`HTTP ${response.status}`);
    const refreshed=await apiFetch(`/api/review-run?runId=${encodeURIComponent(snapshot.runId)}`);const next=await refreshed.json();if(!refreshed.ok)throw new Error(next.error||`ReviewRun refresh HTTP ${refreshed.status}`);
    state.activeReviewRun=next;byId("reviewRunTransitionReason").value="";byId("reviewRunTransitionStatus").textContent=`Immutable ${targetState} receipt ${receipt.receiptSha256}`;renderReviewRunGate();toast(`ReviewRun transitioned to ${targetState}`);
  }catch(error){console.error(error);byId("reviewRunTransitionStatus").textContent=`Transition failed: ${error.message}`;toast(`ReviewRun transition failed: ${error.message}`,true);renderReviewRunGate();}
}

async function exportActiveReviewRun(){
  if(!state.activeReviewRun)return;
  const button=byId("exportReviewRun");button.disabled=true;
  try{
    const response=await apiFetch("/api/review-run-export",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({runId:state.activeReviewRun.runId})});
    const payload=await response.json();if(!response.ok)throw new Error(payload.error||`HTTP ${response.status}`);
    byId("reviewRunExportStatus").textContent=`${payload.exportPath} · ${payload.exportFileSha256}`;
    toast("Immutable admission packet exported");
  }catch(error){console.error(error);byId("reviewRunExportStatus").textContent=`Export failed: ${error.message}`;toast(`ReviewRun export failed: ${error.message}`,true);}
  finally{button.disabled=false;}
}

function renderReplayRun(){
  const section=byId("replayRunSection"),run=state.replayRun;section.hidden=!run;if(!run)return;
  const metrics=byId("replayRunMetrics");metrics.replaceChildren();for(const [label,value] of [["Run",run.runId],["Replay",run.replay.logicalPath],["Replay SHA",run.replay.contentSha256],["Verifier SHA",run.verifier.contentSha256],["Frames",run.verification.frames],["Winner",run.verification.winner],["Truth hash",run.verification.truthHash],["Verifier",run.verification.verdict],["Visual evidence",run.visualStatus],["Capture lineage",run.captureAssociation]])appendMetric(metrics,label,value);
  byId("replayRunScope").textContent=run.reviewScope;const grid=byId("replayCaptureGrid");grid.replaceChildren();for(const capture of run.captures){const card=element("button","evidence-card");card.type="button";const image=element("img");image.src=fileUrl(capture.logicalPath);image.alt=`Replay capture: ${capture.logicalPath}`;card.append(image,element("span",null,capture.logicalPath.split("/").at(-1)));card.addEventListener("click",()=>openEvidence(capture.logicalPath));grid.append(card);}if(!run.captures.length)grid.append(element("div","comment-empty","No visual capture is bound. This run is truth-only and cannot prove presentation quality."));
}

async function submitReplayReview(){
  if(!state.replayRun)return;const button=byId("submitReplayReview");button.disabled=true;try{const response=await apiFetch("/api/replay-report",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reviewRunFingerprint:state.replayRun.fingerprintSha256,decision:byId("replayDecision").value,summary:byId("replaySummary").value})});const payload=await response.json();if(!response.ok)throw new Error(payload.error||`HTTP ${response.status}`);byId("replayReceipt").textContent=`Receipt ${payload.receiptId} · ${payload.submittedBy}`;toast("Replay review submitted");}catch(error){console.error(error);toast(`Replay review failed: ${error.message}`,true);}finally{button.disabled=false;}
}

function renderEvidence(){const grid=byId("evidenceGrid");grid.replaceChildren();const images=state.active?.evidenceImages||[];byId("evidenceCount").textContent=String(images.length);for(const path of images){const card=element("button","evidence-card");card.type="button";const image=element("img");image.src=fileUrl(path);image.alt=`QA evidence: ${path.split("/").at(-1)}`;image.loading="lazy";card.append(image,element("span",null,path.split("/").at(-1)));card.addEventListener("click",()=>openEvidence(path));grid.append(card);}if(!images.length)grid.append(element("div","comment-empty","No adjacent QA images were indexed for this artifact."));}
function openEvidence(path){byId("imageDialogPreview").src=fileUrl(path);byId("imageDialogCaption").textContent=path;byId("imageDialog").showModal();}

function setupAnimationForModel(model){
  const available=Boolean(model.animations?.length);byId("animationBar").hidden=!available;byId("neuralGateSection").hidden=!available;$(".viewport-panel").classList.toggle("has-animation",available);state.renderer.animationPlaying=false;
  const clips=byId("animationClip");clips.replaceChildren();if(!available)return;
  model.animations.forEach((clip,index)=>{const option=element("option",null,`${clip.name} · ${clip.duration.toFixed(2)}s`);option.value=String(index);clips.append(option);});clips.value=String(model.activeAnimation);updateAnimationUi();
}
function updateAnimationUi(){const model=state.renderer?.primary;if(!model?.animations?.length)return;const clip=model.animations[model.activeAnimation];byId("animationTimeline").max=String(clip.duration);byId("animationTimeline").value=String(model.animationTime);byId("animationTime").textContent=`${model.animationTime.toFixed(2)} / ${clip.duration.toFixed(2)}s`;byId("animationPlay").textContent=state.renderer.animationPlaying?"❚❚":"▶";}
function renderNeuralGate(){
  const section=byId("neuralGateSection"),hasAnimation=Boolean(state.renderer?.primary?.animations?.length);section.hidden=!hasAnimation;if(!hasAnimation)return;
  const gate=state.review?.neuralMotion||{status:"not-evaluated",criteria:{},summary:""};const status=byId("neuralGateStatus");status.textContent=gate.status.replaceAll("-"," ");status.className=`neural-status ${gate.status}`;
  const root=byId("neuralCriteria");root.replaceChildren();for(const [key,label] of NEURAL_CRITERIA_UI){const verdict=gate.criteria?.[key]?.verdict||"not-evaluated";const row=element("div","neural-criterion");row.append(element("span",null,label),element("span",`criterion-verdict ${verdict}`,verdict.replace("not-evaluated","pending")));root.append(row);}
  byId("neuralSummary").textContent=gate.summary||("Evidence: "+(gate.evidencePath||"not captured")+". Hermes neural vision assessment is required before human approval.");
}
async function captureNeuralEvidence(){
  const renderer=state.renderer,model=renderer.primary;if(!model?.animations?.length){toast("This asset has no animation clips",true);return;}if(state.active.local){toast("Repository evidence requires an indexed asset",true);return;}
  const wasPlaying=renderer.animationPlaying,original=model.animationTime,clip=model.animations[model.activeAnimation];renderer.animationPlaying=false;byId("neuralCapture").disabled=true;byId("neuralCapture").textContent="Capturing 8 frames…";
  try{const sheet=document.createElement("canvas");sheet.width=1600;sheet.height=900;const context=sheet.getContext("2d");context.fillStyle="#090b0d";context.fillRect(0,0,sheet.width,sheet.height);
    for(let index=0;index<8;index+=1){const time=clip.duration*(index/7);renderer.setAnimationTime(time);renderer.renderSnapshot();const x=(index%4)*400,y=Math.floor(index/4)*450;context.drawImage(renderer.canvas,x,y,400,450);context.fillStyle="rgba(0,0,0,.78)";context.fillRect(x+8,y+8,116,23);context.fillStyle="#f0bd58";context.font="12px ui-monospace, monospace";context.fillText(`F${index+1} · ${time.toFixed(3)}s`,x+15,y+24);}
    const pngDataUrl=sheet.toDataURL("image/png");const response=await apiFetch("/api/neural-evidence",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({assetPath:state.active.path,artifact:state.review.artifact,clip:clip.name,pngDataUrl})});const receipt=await response.json();if(!response.ok)throw new Error(receipt.error||`HTTP ${response.status}`);
    state.review.neuralMotion={status:"awaiting-neural-review",clip:clip.name,model:"",evaluatedAt:null,evidencePath:receipt.evidencePath,evidenceSha256:receipt.evidenceSha256,summary:"Deterministic eight-frame contact sheet captured. Awaiting Hermes neural visual assessment; human approval remains blocked.",criteria:{}};renderNeuralGate();scheduleSave();toast("Neural evidence saved; Hermes review required");
  }catch(error){console.error(error);toast(`Neural evidence failed: ${error.message}`,true);}finally{renderer.setAnimationTime(original);renderer.animationPlaying=wasPlaying;byId("neuralCapture").disabled=false;byId("neuralCapture").textContent="Prepare neural gate";}
}

function renderReview(){renderDecision();renderChecklist();renderNeuralGate();renderComments();renderReportSubmission();}
function renderDecision(){for(const button of $$('[data-decision]'))button.classList.toggle("is-active",button.dataset.decision===state.review?.decision);}
function renderChecklist(){const root=byId("checklist");root.replaceChildren();for(const [key,label] of CHECKS){const row=element("div","check-row");const name=element("label",null,label);const select=element("select");select.dataset.key=key;for(const [value,text] of CHECK_OPTIONS){const option=element("option",null,text);option.value=value;select.append(option);}select.value=state.review?.checklist?.[key]||"unchecked";select.dataset.state=select.value;select.addEventListener("change",()=>{select.dataset.state=select.value;state.review.checklist[key]=select.value;scheduleSave();});row.append(name,select);root.append(row);}}

function renderComments(){const list=byId("commentList");list.replaceChildren();const comments=state.review?.comments||[];const open=comments.filter(comment=>comment.status==="open").length;byId("openCommentCount").textContent=String(open);comments.forEach((comment,index)=>{const card=element("article","comment-card");card.dataset.id=comment.id;card.classList.toggle("is-resolved",comment.status!=="open");const meta=element("div","comment-meta");const number=element("span","comment-index",String(index+1));const category=element("span","comment-pill",comment.category);const severity=element("span",`comment-pill ${comment.severity}`,comment.severity);meta.append(number,category,severity);if(comment.point)meta.append(element("span","comment-pill","surface pin"));card.append(meta,element("p",null,comment.text));const actions=element("div","comment-actions");if(comment.point){const focus=element("button",null,"Focus");focus.type="button";focus.addEventListener("click",()=>focusComment(comment,card));actions.append(focus);}const resolve=element("button",null,comment.status==="open"?"Resolve":"Reopen");resolve.type="button";resolve.addEventListener("click",()=>{comment.status=comment.status==="open"?"resolved":"open";scheduleSave();renderComments();});const remove=element("button",null,"Delete");remove.type="button";remove.addEventListener("click",()=>{state.review.comments=state.review.comments.filter(item=>item.id!==comment.id);scheduleSave();renderComments();});actions.append(resolve,remove);card.append(actions);list.append(card);});if(!comments.length)list.append(element("div","comment-empty","No review notes yet. Add a general note or place a pin directly on model geometry."));}

function renderReportSubmission(){const submission=state.review?.submission||null,taskPlan=state.review?.taskPlan||null,summary=byId("reportSummary"),status=byId("reportSubmissionStatus"),receipt=byId("reportReceipt"),planStatus=byId("reportPlanStatus"),local=Boolean(state.active?.local);if(document.activeElement!==summary)summary.value=state.review?.reportSummary||"";status.textContent=submission?"Submitted":"Draft";status.classList.toggle("is-submitted",Boolean(submission));receipt.textContent=submission?`Receipt ${submission.receiptId} · ${new Date(submission.submittedAt).toLocaleString()}`:(local?"Local files cannot be submitted. Export the brief instead.":"Choose a decision, then submit this review directly.");planStatus.textContent=taskPlan?`${taskPlan.tasks.length} implementation tasks · adversarially verified`:(submission?"Submitted report queued for specialized planning and adversarial verification.":"Task planning starts after submission.");for(const button of [byId("submitReportButton"),byId("submitReportInline")])button.disabled=local||!state.review;}

function focusComment(comment,card){if(comment.camera)state.renderer.applyCamera(comment.camera);card.classList.add("is-focused");setTimeout(()=>card.classList.remove("is-focused"),1200);}
function renderPins(){const layer=byId("pinLayer");layer.replaceChildren();if(!state.review||!state.renderer?.primary)return;let index=0;for(const comment of state.review.comments){if(!comment.point)continue;index+=1;const screen=state.renderer.project(comment.point.world);if(!screen?.visible)continue;const pin=element("button","surface-pin",String(index));pin.type="button";pin.style.left=`${screen.x}px`;pin.style.top=`${screen.y}px`;pin.dataset.severity=comment.severity;pin.classList.toggle("is-resolved",comment.status!=="open");pin.title=comment.text;pin.addEventListener("click",()=>{$$('[data-tab="review"]')[0].click();const card=$(`.comment-card[data-id="${CSS.escape(comment.id)}"]`);card?.scrollIntoView({block:"center"});if(card)focusComment(comment,card);});layer.append(pin);}}

function handlePinClick(event){const hit=state.renderer.pick(event);if(!hit){toast("No model surface under cursor",true);return;}state.pendingPoint={world:hit.world.map(value=>Number(value.toFixed(6))),normal:hit.normal.map(value=>Number(value.toFixed(6)))};openComposer(state.pendingPoint);togglePinMode(false);}
function openComposer(point=null){state.pendingPoint=point;byId("composerPoint").textContent=point?`Surface · ${point.world.map(value=>value.toFixed(3)).join(", ")}`:"General comment";byId("commentText").value="";byId("commentComposer").hidden=false;byId("commentText").focus();}
function closeComposer(){state.pendingPoint=null;byId("commentComposer").hidden=true;}
function togglePinMode(force){state.pinMode=force===undefined?!state.pinMode:force;byId("pinTool").classList.toggle("is-active",state.pinMode);byId("viewport").classList.toggle("is-pinning",state.pinMode);if(state.pinMode)toast("Click directly on model geometry to place the comment pin");}

function scheduleSave(){if(!state.review||!state.active)return;if(state.review.submission){state.review.submission=null;state.review.taskPlan=null;renderReportSubmission();}if(state.active.local){setSaveState("Local review · export only");return;}setSaveState("Saving…","saving");clearTimeout(state.saveTimer);state.saveTimer=setTimeout(saveReview,280);}
async function saveReview(){try{const response=await apiFetch("/api/review",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(state.review)});const payload=await response.json();if(!response.ok)throw new Error(payload.error||`HTTP ${response.status}`);state.review=payload;setSaveState("Saved","saved");renderDecision();}catch(error){console.error(error);setSaveState("Save failed","error");toast(`Review save failed: ${error.message}`,true);}}

async function submitReport(){if(!state.review||!state.active)return;if(state.active.local){toast("Local files are export-only",true);return;}if(["webgl_context_lost","recapture_required","viewer_unsupported"].includes(state.visualEvidence.status)){toast("Submission blocked: visual evidence is invalid or unsupported; recapture with an exact viewer",true);return;}if(state.review.decision==="pending"){toast("Choose Approve, Request changes, or Reject before submitting",true);activateTab("review");return;}clearTimeout(state.saveTimer);const buttons=[byId("submitReportButton"),byId("submitReportInline")];buttons.forEach(button=>{button.disabled=true;button.textContent="Submitting…";});let submitted=false;try{const response=await apiFetch("/api/report",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(state.review)});const payload=await response.json();if(!response.ok)throw new Error(payload.error||`HTTP ${response.status}`);state.review=payload;submitted=true;setSaveState("Report submitted","saved");renderReview();toast(`Report submitted · ${payload.submission.receiptId}`);setTimeout(()=>window.close(),350);}catch(error){console.error(error);setSaveState("Submission failed","error");toast(`Report submission failed: ${error.message}`,true);}finally{if(!submitted){buttons[0].textContent="Submit report";buttons[1].textContent="Submit human report";renderReportSubmission();}}}

function exportBrief(){if(!state.active||!state.review){toast("Select an asset before exporting",true);return;}const m=state.active.metrics||{};const lines=[`# Asset review — ${state.active.family}`,"",`- Artifact: \`${state.active.path}\``,`- Stage: ${state.active.stage}`,`- Decision: **${state.review.decision}**`,`- Triangles: ${formatNumber(m.triangles)}`,`- Vertices: ${formatNumber(m.vertices)}`,`- File size: ${formatBytes(m.bytes)}`,`- Review JSON: \`qa_runs/asset_reviews/${state.active.id}.json\``,"","## Acceptance matrix","",...CHECKS.map(([key,label])=>`- ${label}: ${state.review.checklist[key]||"unchecked"}`),"","## Comments",""];
  if(!state.review.comments.length)lines.push("No comments.");else state.review.comments.forEach((comment,index)=>{lines.push(`${index+1}. **${comment.severity} · ${comment.category} · ${comment.status}** — ${comment.text}${comment.point?` (surface: ${comment.point.world.join(", ")})`:""}`);});
  lines.push("","## Human report","",state.review.reportSummary||"No summary.","",`Submission receipt: ${state.review.submission?.receiptId||"not submitted"}`);const blob=new Blob([`${lines.join("\n")}\n`],{type:"text/markdown"});downloadBlob(blob,`${state.active.family}-${state.active.stage.toLowerCase().replaceAll(/[^a-z0-9]+/g,"-")}-review.md`);toast("Review brief exported");}
function downloadBlob(blob,name){const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);}

function setupCommands(){const commands=[
  ["P","Add surface pin",()=>togglePinMode(true)],
  ["F","Frame selected asset",()=>state.renderer.frameModel()],
  ["1","Material diagnostic",()=>setViewMode("material")],
  ["2","Clay diagnostic",()=>setViewMode("clay")],
  ["3","Normal diagnostic",()=>setViewMode("normals")],
  ["4","Wireframe diagnostic",()=>setViewMode("wireframe")],
  ["E","Export review brief",exportBrief],
  ["S","Submit human report",submitReport],
  ["C","Capture viewport PNG",captureViewport],
  ["R","Open review inspector",()=>activateTab("review")],
  ["D","Open technical details",()=>activateTab("details")],
];
  const render=(query="")=>{const list=byId("commandList");list.replaceChildren();for(const [key,label,action] of commands.filter(command=>command[1].toLowerCase().includes(query.toLowerCase()))){const button=element("button","command-item");button.type="button";button.append(element("span",null,key),element("span",null,label),element("small",null,"Run"));button.addEventListener("click",()=>{byId("commandDialog").close();action();});list.append(button);}};render();byId("commandSearch").addEventListener("input",event=>render(event.target.value));byId("commandButton").addEventListener("click",()=>{byId("commandDialog").showModal();byId("commandSearch").focus();});
}
function setViewMode(mode){state.renderer.viewMode=mode;for(const button of $$('[data-view-mode]'))button.classList.toggle("is-active",button.dataset.viewMode===mode);}
function activateTab(tab){for(const button of $$(".inspector-tab"))button.classList.toggle("is-active",button.dataset.tab===tab);for(const panel of $$(".tab-content"))panel.classList.toggle("is-active",panel.dataset.tabPanel===tab);}
function captureViewport(){if(!state.renderer.primary){toast("Load a model before capture",true);return;}if(state.renderer.contextLost){toast("Capture blocked: WebGL context is lost",true);return;}try{state.renderer.renderSnapshot();state.renderer.canvas.toBlob(blob=>{if(!blob)return;downloadBlob(blob,`${state.active?.family||"local-model"}-viewport.png`);if(state.visualEvidence.status==="recapture_required"&&state.activeReviewRun){recordViewerContextEvent("recaptured",blob).then(()=>{setVisualEvidenceStatus("captured");toast("Viewport PNG captured and server-bound recapture completed");}).catch(error=>toast(error.message,true));}else{setVisualEvidenceStatus("captured");toast("Viewport PNG captured");}},"image/png");}catch(error){setVisualEvidenceStatus("recapture_required",error.message);toast(`Capture failed: ${error.message}`,true);}}

function motionFrame(){return Number(byId("motionLabFrame")?.value||0);}
function setMotionFrame(frame){const lab=state.motionLab?.motionLab;if(!lab)return;const value=Math.max(0,Math.min(lab.frameCount-1,Math.round(frame)));byId("motionLabFrame").value=String(value);renderMotionLab();}
function motionFrameRecord(view, frame){return [...view.frames].sort((a,b)=>Math.abs(a.frame-frame)-Math.abs(b.frame-frame))[0]||null;}
function motionCandidateView(candidateId){const lab=state.motionLab?.motionLab;const candidate=lab?.candidates.find(item=>item.id===candidateId);return lab?.views.find(item=>item.id===candidate?.viewId)||null;}
function drawMotionPlot(canvas, series){const width=Math.max(1,Math.floor(canvas.clientWidth*devicePixelRatio)),height=Math.max(1,Math.floor(canvas.clientHeight*devicePixelRatio));canvas.width=width;canvas.height=height;const ctx=canvas.getContext("2d");ctx.clearRect(0,0,width,height);const min=Math.min(...series),max=Math.max(...series),span=Math.max(max-min,1e-9);ctx.strokeStyle="rgba(255,255,255,.13)";ctx.beginPath();ctx.moveTo(0,height-.5);ctx.lineTo(width,height-.5);ctx.stroke();ctx.strokeStyle="#62b9b5";ctx.lineWidth=Math.max(1,devicePixelRatio);ctx.beginPath();series.forEach((value,index)=>{const x=series.length===1?0:index/(series.length-1)*width;const y=height-(value-min)/span*(height-4)-2;if(index)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();const frame=motionFrame();if(frame<series.length){ctx.strokeStyle="#f0bd58";ctx.beginPath();const x=series.length===1?0:frame/(series.length-1)*width;ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke();}}
function renderMotionTimeline(lab){const root=byId("motionTimeline");root.replaceChildren();for(const name of ["text","fullBody","root","endEffectors","contacts"]){const row=element("div","motion-track"),label=element("span","motion-track-label",name),rail=element("div","motion-track-rail");const place=event=>{const rect=rail.getBoundingClientRect();setMotionFrame((event.clientX-rect.left)/Math.max(rect.width,1)*(lab.frameCount-1));};rail.addEventListener("pointerdown",event=>{rail.setPointerCapture(event.pointerId);place(event);});rail.addEventListener("pointermove",event=>{if(rail.hasPointerCapture(event.pointerId))place(event);});for(const entry of lab.tracks[name]){const pin=element("button","motion-track-pin",name);pin.type="button";pin.dataset.track=name;pin.style.left=`${entry.frame/Math.max(1,lab.frameCount-1)*100}%`;pin.title=`${name} · frame ${entry.frame}`;pin.addEventListener("click",event=>{event.stopPropagation();setMotionFrame(entry.frame);});rail.append(pin);}row.append(label,rail);root.append(row);}}
function drawMotionSkeleton(canvas,view,sample,color="#62b9b5",overlay=null){
  const scale=devicePixelRatio,width=Math.max(260,Math.floor(canvas.clientWidth||300)),height=220;canvas.width=Math.floor(width*scale);canvas.height=Math.floor(height*scale);const ctx=canvas.getContext("2d");ctx.scale(scale,scale);ctx.clearRect(0,0,width,height);
  const groups=[{view,sample,color},...(overlay?[overlay]:[])],all=groups.flatMap(group=>group.sample?.joints||[]);if(!all.length){ctx.fillStyle="#8d98a7";ctx.fillText("Root-only payload",12,22);return;}
  const xs=all.map(point=>point[0]),ys=all.map(point=>point[1]);const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys),spanX=Math.max(maxX-minX,.25),spanY=Math.max(maxY-minY,.25),fit=Math.min((width-28)/spanX,(height-32)/spanY),project=point=>[14+(point[0]-minX)*fit,height-16-(point[1]-minY)*fit];
  for(const group of groups){const joints=group.sample?.joints;if(!joints)continue;ctx.strokeStyle=group.color;ctx.lineWidth=1.5;ctx.globalAlpha=.88;for(let index=0;index<joints.length;index+=1){const parent=group.view.parents?.[index];if(parent==null||parent<0)continue;const a=project(joints[parent]),b=project(joints[index]);ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();}ctx.fillStyle=group.color;for(const point of joints){const xy=project(point);ctx.beginPath();ctx.arc(xy[0],xy[1],2.3,0,Math.PI*2);ctx.fill();}ctx.globalAlpha=1;}
  canvas._motionProjection={view,sample,project,fit,points:(sample.joints||[]).map((point,index)=>({index,world:point,screen:project(point)}))};
}
function bindMotionSkeletonPins(canvas){if(canvas.dataset.pinBound)return;canvas.dataset.pinBound="true";const setFrom=(event,drag=false)=>{const projection=canvas._motionProjection;if(!projection)return;const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;if(!drag){const nearest=projection.points.reduce((best,point)=>{const distance=Math.hypot(point.screen[0]-x,point.screen[1]-y);return !best||distance<best.distance?{...point,distance}:best;},null);if(!nearest||nearest.distance>24)return;canvas._motionDrag={joint:nearest.index,world:[...nearest.world],start:[x,y]};}const state=canvas._motionDrag;if(!state)return;const world=[state.world[0]+(x-state.start[0])/projection.fit,state.world[1]-(y-state.start[1])/projection.fit,state.world[2]];byId("motionJointId").value=projection.view.jointNames?.[state.joint]||`joint-${state.joint}`;byId("motionWorldX").value=world[0].toFixed(5);byId("motionWorldY").value=world[1].toFixed(5);byId("motionWorldZ").value=world[2].toFixed(5);};canvas.addEventListener("pointerdown",event=>{canvas.setPointerCapture(event.pointerId);setFrom(event,false);});canvas.addEventListener("pointermove",event=>{if(canvas.hasPointerCapture(event.pointerId))setFrom(event,true);});canvas.addEventListener("pointerup",event=>{setFrom(event,true);canvas._motionDrag=null;canvas.releasePointerCapture(event.pointerId);});}
function renderMotionLab(){
  const snapshot=state.motionLab,panel=byId("motionLabPanel");panel.hidden=!snapshot;if(!snapshot)return;const lab=snapshot.motionLab,frame=motionFrame();byId("motionLabStatus").textContent="Bound payload";byId("motionLabStatus").classList.add("is-submitted");byId("motionLabIdentity").textContent=`${lab.motionLabId} · revision ${lab.revision} · ${lab.fps} Hz · source ${snapshot.source.sha256}`;const slider=byId("motionLabFrame");slider.max=String(lab.frameCount-1);if(Number(slider.value)>=lab.frameCount)slider.value="0";byId("motionLabFrameOutput").textContent=`F${frame} / ${lab.frameCount-1}`;
  for(const select of [byId("motionCandidateA"),byId("motionCandidateB")]){const old=select.value;select.replaceChildren();for(const candidate of lab.candidates){const option=element("option",null,candidate.label);option.value=candidate.id;select.append(option);}select.value=lab.candidates.some(item=>item.id===old)?old:(select.id==="motionCandidateA"?lab.candidates[0].id:lab.candidates[1].id);}renderMotionTimeline(lab);
  const views=byId("motionViews");views.replaceChildren();for(const view of lab.views){const sample=motionFrameRecord(view,frame),card=element("article","motion-view"),canvas=document.createElement("canvas");canvas.className="motion-skeleton-canvas";canvas.setAttribute("aria-label",`${view.label} synchronized skeleton at frame ${frame}`);card.append(element("h3",null,view.label),canvas,element("p",null,`frame ${sample?.frame??"not sampled"} · root ${(sample?.root||[]).map(value=>Number(value).toFixed(3)).join(", ")||"unavailable"}`));views.append(card);drawMotionSkeleton(canvas,view,sample);bindMotionSkeletonPins(canvas);}
  const viewA=motionCandidateView(byId("motionCandidateA").value),viewB=motionCandidateView(byId("motionCandidateB").value),sampleA=motionFrameRecord(viewA,frame),sampleB=motionFrameRecord(viewB,frame),difference=byId("motionDifference");difference.replaceChildren();difference.append(element("strong",null,`Difference overlay · Δ root ${sampleA&&sampleB?sampleA.root.map((value,index)=>(sampleB.root[index]-value).toFixed(4)).join(", "):"unavailable"} m`));const diffCanvas=document.createElement("canvas");diffCanvas.className="motion-difference-canvas";difference.append(diffCanvas);drawMotionSkeleton(diffCanvas,viewA,sampleA,"#62b9b5",sampleB?.joints?{view:viewB,sample:sampleB,color:"#f0bd58"}:null);
  const plots=byId("motionPlots");plots.replaceChildren();for(const [key,label] of [["fkResidual","FK residual"],["footDrift","Foot drift"],["com","COM"],["grip","Grip"],["weaponPath","Weapon path"]]){const card=element("article","motion-plot"),head=element("div","motion-plot-head");head.append(element("span",null,label),element("small",null,lab.metrics[key].unit));const canvas=document.createElement("canvas");card.append(head,canvas);plots.append(card);drawMotionPlot(canvas,lab.metrics[key].series);}
  const events=byId("motionEvents");events.replaceChildren();for(const receipt of snapshot.events){const row=element("article","motion-event");row.append(element("strong",null,`${receipt.sequence} · ${receipt.eventType}`),element("span",null,receipt.eventType==="annotation"?`${receipt.reviewerKind} · F${receipt.frame} · ${receipt.jointId}/${receipt.objectId}`:`${receipt.reviewerKind} · ${receipt.action}`),element("p",null,receipt.text||receipt.comment||""),element("code",null,receipt.eventSha256));events.append(row);}if(!snapshot.events.length)events.append(element("p","muted","No append-only Motion Lab events recorded."));
}
async function loadMotionLab(){const response=await apiFetch("/api/motion-lab");if(response.status===404){state.motionLab=null;renderMotionLab();return;}const payload=await response.json();if(!response.ok)throw new Error(payload.error||`Motion Lab HTTP ${response.status}`);state.motionLab=payload;renderMotionLab();}
async function appendMotionAnnotation(event){event.preventDefault();const snapshot=state.motionLab;if(!snapshot)return;const text=byId("motionAnnotationText").value.trim();const coordinates=[byId("motionWorldX"),byId("motionWorldY"),byId("motionWorldZ")].map(input=>Number(input.value));if(!text||coordinates.some(value=>!Number.isFinite(value))){toast("Motion Lab annotations require text and finite world coordinates",true);return;}const lab=snapshot.motionLab,button=$("button[type=submit]",byId("motionAnnotationForm"));button.disabled=true;try{const response=await apiFetch("/api/motion-lab-annotation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({motionLabId:lab.motionLabId,sourceSha256:snapshot.source.sha256,reviewerKind:byId("motionReviewerKind").value,text,revision:lab.revision,frame:motionFrame(),jointId:byId("motionJointId").value.trim(),objectId:byId("motionObjectId").value.trim(),worldPoint:coordinates})});const payload=await response.json();if(!response.ok)throw new Error(payload.error||`Motion Lab annotation HTTP ${response.status}`);byId("motionAnnotationText").value="";await loadMotionLab();toast("Append-only Motion Lab annotation recorded");}catch(error){console.error(error);toast(error.message,true);}finally{button.disabled=false;}}

function bindUi(){
  byId("motionLabFrame").addEventListener("input",()=>renderMotionLab());
  byId("motionCandidateA").addEventListener("change",renderMotionLab);
  byId("motionCandidateB").addEventListener("change",renderMotionLab);
  byId("motionAnnotationForm").addEventListener("submit",appendMotionAnnotation);
  byId("assetSearch").addEventListener("input",renderLibrary);
  byId("submitReplayReview").addEventListener("click",submitReplayReview);
  byId("exportReviewRun").addEventListener("click",exportActiveReviewRun);
  byId("reviewRunFail").addEventListener("click",()=>transitionActiveReviewRun("fail"));
  byId("reviewRunSupersede").addEventListener("click",()=>transitionActiveReviewRun("superseded"));
  for(const chip of $$(".filter-chip"))chip.addEventListener("click",()=>{state.stageFilter=chip.dataset.stage;for(const item of $$(".filter-chip"))item.classList.toggle("is-active",item===chip);renderLibrary();});
  for(const button of $$('[data-view-mode]'))button.addEventListener("click",()=>setViewMode(button.dataset.viewMode));
  byId("gridToggle").addEventListener("click",event=>{state.renderer.grid=!state.renderer.grid;event.currentTarget.classList.toggle("is-active",state.renderer.grid);});
  byId("compareToggle").addEventListener("click",event=>{const active=event.currentTarget.classList.toggle("is-active");if(active){state.renderer.comparison=state.renderer._hiddenComparison||state.renderer.comparison;}else{state.renderer._hiddenComparison=state.renderer.comparison;state.renderer.comparison=null;}});
  byId("compareSlot").addEventListener("click",()=>toast("Use the Compare button on another library asset"));
  byId("pinTool").addEventListener("click",()=>togglePinMode());byId("resetCamera").addEventListener("click",()=>state.renderer.frameModel());byId("captureButton").addEventListener("click",captureViewport);byId("exportButton").addEventListener("click",exportBrief);byId("submitReportButton").addEventListener("click",submitReport);byId("submitReportInline").addEventListener("click",submitReport);
  byId("animationPlay").addEventListener("click",()=>{state.renderer.animationPlaying=!state.renderer.animationPlaying;updateAnimationUi();});
  byId("animationClip").addEventListener("change",event=>state.renderer.setAnimationClip(Number(event.target.value)));
  byId("animationTimeline").addEventListener("input",event=>{state.renderer.animationPlaying=false;state.renderer.setAnimationTime(Number(event.target.value));});
  byId("animationSpeed").addEventListener("change",event=>{state.renderer.animationSpeed=Number(event.target.value);});
  byId("animationLoop").addEventListener("click",event=>{state.renderer.animationLoop=!state.renderer.animationLoop;event.currentTarget.classList.toggle("is-active",state.renderer.animationLoop);});
  byId("neuralCapture").addEventListener("click",captureNeuralEvidence);
  for(const tab of $$(".inspector-tab"))tab.addEventListener("click",()=>activateTab(tab.dataset.tab));
  for(const button of $$('[data-decision]'))button.addEventListener("click",()=>{if(!state.review)return;if(button.dataset.decision==="approved"&&["webgl_context_lost","recapture_required","viewer_unsupported"].includes(state.visualEvidence.status)){toast("Approval blocked: visual evidence is invalid or unsupported; recapture with an exact viewer",true);return;}if(button.dataset.decision==="approved"&&state.renderer.primary?.animations?.length&&state.review.neuralMotion?.status!=="pass"){toast("Approval blocked: animation requires a passing neural visual audit",true);return;}state.review.decision=button.dataset.decision;scheduleSave();renderDecision();});
  byId("resetChecklist").addEventListener("click",()=>{if(!state.review)return;state.review.checklist={};renderChecklist();scheduleSave();});
  byId("addGeneralComment").addEventListener("click",()=>openComposer());byId("cancelComment").addEventListener("click",closeComposer);
  byId("reportSummary").addEventListener("input",event=>{if(!state.review)return;state.review.reportSummary=event.target.value;scheduleSave();});byId("reportSummary").addEventListener("keydown",event=>{if((event.ctrlKey||event.metaKey)&&event.key==="Enter"){event.preventDefault();submitReport();}});
  byId("saveComment").addEventListener("click",()=>{const text=byId("commentText").value.trim();if(!text){toast("Comment text is required",true);return;}const comment={id:`pin-${crypto.randomUUID()}`,text,category:byId("commentCategory").value,severity:byId("commentSeverity").value,status:"open",author:"human",createdAt:new Date().toISOString(),point:state.pendingPoint,camera:state.pendingPoint?state.renderer.cameraSnapshot():null};state.review.comments.push(comment);closeComposer();renderComments();scheduleSave();});
  for(const category of CATEGORIES){const option=element("option",null,category);option.value=category;byId("commentCategory").append(option);}for(const severity of SEVERITIES){const option=element("option",null,severity);option.value=severity;byId("commentSeverity").append(option);}byId("commentSeverity").value="major";
  byId("fileInput").addEventListener("change",async event=>{const file=event.target.files?.[0];if(!file)return;try{const record={id:`local-${Date.now()}`,family:file.name.replace(/\.glb$/i,""),name:file.name,stage:"Local inspection",path:file.name,local:true,metrics:{bytes:file.size},evidenceImages:[]};state.active=record;state.review={schemaVersion:1,assetPath:`local/${file.name}`,decision:"pending",checklist:{},comments:[],reportSummary:"",submission:null};await loadModel(record,false,await file.arrayBuffer());byId("familyCrumb").textContent="Local file";byId("assetCrumb").textContent=file.name;byId("activeSlot").textContent=file.name;setSaveState("Local review · export only");renderReview();renderAssetMetadata();renderEvidence();toast("Local GLB loaded; repository persistence is disabled for local files");}catch(error){console.error(error);toast(error.message,true);}});
  byId("imageDialog").addEventListener("click",event=>{if(event.target===byId("imageDialog"))byId("imageDialog").close();});
  window.addEventListener("keydown",event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="k"){event.preventDefault();byId("commandButton").click();return;}if(event.target.matches("input,textarea,select"))return;if(event.key.toLowerCase()==="p")togglePinMode();if(event.key.toLowerCase()==="f")state.renderer.frameModel();if(event.key==="1")setViewMode("material");if(event.key==="2")setViewMode("clay");if(event.key==="3")setViewMode("normals");if(event.key==="4")setViewMode("wireframe");});
  setupCommands();
}

async function init(){
  try{state.renderer=new Renderer(byId("glCanvas"));window.__forgeLens=state;bindUi();const sessionResponse=await fetch("/api/session",{credentials:"same-origin"});if(!sessionResponse.ok)throw new Error(`Browser authority HTTP ${sessionResponse.status}`);state.authority=await sessionResponse.json();const [response,replayResponse,activeRunResponse]=await Promise.all([apiFetch("/api/catalog"),apiFetch("/api/replay-run"),apiFetch("/api/active-review-run")]);if(!response.ok)throw new Error(`Catalog HTTP ${response.status}`);if(!replayResponse.ok)throw new Error(`Replay HTTP ${replayResponse.status}`);if(!activeRunResponse.ok)throw new Error(`Active ReviewRun HTTP ${activeRunResponse.status}`);const catalog=await response.json();state.replayRun=await replayResponse.json();state.activeReviewRun=await activeRunResponse.json();renderReplayRun();renderReviewRunGate();await loadMotionLab();state.catalog=catalog.assets||[];renderLibrary();const requested=new URLSearchParams(location.search).get("asset")||catalog.initialAsset;const initial=state.catalog.find(record=>record.path===requested)||state.catalog[0];if(initial)await selectAsset(initial);else byId("viewportEmpty").querySelector("p").textContent="No GLB files were indexed under assets/.";}
  catch(error){console.error(error);toast(`Studio initialization failed: ${error.message}`,true);byId("viewportEmpty").querySelector("h2").textContent="Initialization failed";byId("viewportEmpty").querySelector("p").textContent=error.message;}
}

init();
