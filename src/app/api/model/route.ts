import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

// ─── Types ──────────────────────────────────────────────────────────────────

interface ModelDetail {
  id: string;
  category: string;
  fileSize: number;
  fileSizeFormatted: string;
  meta: {
    formatVersion: string;
    modelFormat: string;
    modelIdentifier: string;
    boxUv: boolean;
  } | null;
  boneCount: number;
  elementCount: number;
  animationCount: number;
  animationNames: string[];
  textureDimensions: {
    width: number;
    height: number;
  } | null;
  resolution: {
    width: number;
    height: number;
  } | null;
  groups: number;
  largeFile: boolean;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

// Threshold: files above this skip full JSON parse to avoid OOM
const LARGE_FILE_THRESHOLD = 50 * 1024 * 1024; // 50 MB

/**
 * Read the first N bytes of a file as a UTF-8 string.
 * Used for extracting meta/resolution from large files without full parsing.
 */
function readHead(filePath: string, maxBytes: number): string {
  const fd = fs.openSync(filePath, "r");
  const size = Math.min(maxBytes, fs.fstatSync(fd).size);
  const buf = Buffer.alloc(size);
  fs.readSync(fd, buf, 0, size, 0);
  fs.closeSync(fd);
  return buf.toString("utf-8");
}

/**
 * Extract stats from the head portion of a large .bbmodel file
 * without parsing the full JSON. Only meta, resolution, and approximate
 * counts are available.
 */
function parseBbmodelStatsPartial(filePath: string): {
  meta: ModelDetail["meta"];
  elementCount: number;
  animationCount: number;
  animationNames: string[];
  textureDimensions: ModelDetail["textureDimensions"];
  resolution: ModelDetail["resolution"];
  groups: number;
} {
  // Read first 128KB which should contain meta, resolution, and start of arrays
  const head = readHead(filePath, 128 * 1024);

  let meta: ModelDetail["meta"] = null;
  const metaMatch = head.match(/"meta"\s*:\s*\{([^}]*)\}/);
  if (metaMatch) {
    const block = metaMatch[1];
    meta = {
      formatVersion: block.match(/"format_version"\s*:\s*"([^"]*)"/)?.[1] || "unknown",
      modelFormat: block.match(/"model_format"\s*:\s*"([^"]*)"/)?.[1] || "unknown",
      modelIdentifier: block.match(/"model_identifier"\s*:\s*"([^"]*)"/)?.[1] || "unknown",
      boxUv: block.match(/"box_uv"\s*:\s*(true|false)/)?.[1] === "true",
    };
  }

  let resolution: ModelDetail["resolution"] = null;
  const resMatch = head.match(
    /"resolution"\s*:\s*\{\s*"width"\s*:\s*(\d+)\s*,\s*"height"\s*:\s*(\d+)\s*\}/
  );
  if (resMatch) {
    resolution = { width: parseInt(resMatch[1], 10), height: parseInt(resMatch[2], 10) };
  }

  // For large files, we cannot get exact counts without full parse.
  // Return -1 to indicate "unavailable due to large file size"
  return {
    meta,
    elementCount: -1,
    animationCount: -1,
    animationNames: [],
    textureDimensions: null,
    resolution,
    groups: -1,
  };
}

/**
 * Parse a .bbmodel file fully. Used for files under the size threshold.
 */
function parseBbmodelStatsFull(filePath: string): {
  meta: ModelDetail["meta"];
  elementCount: number;
  animationCount: number;
  animationNames: string[];
  textureDimensions: ModelDetail["textureDimensions"];
  resolution: ModelDetail["resolution"];
  groups: number;
} {
  const content = fs.readFileSync(filePath, "utf-8");
  const data = JSON.parse(content);

  const meta = data.meta
    ? {
        formatVersion: data.meta.format_version || "unknown",
        modelFormat: data.meta.model_format || "unknown",
        modelIdentifier: data.meta.model_identifier || "unknown",
        boxUv: data.meta.box_uv ?? false,
      }
    : null;

  const elementCount = Array.isArray(data.elements) ? data.elements.length : 0;

  let animationCount = 0;
  const animationNames: string[] = [];
  if (Array.isArray(data.animations)) {
    animationCount = data.animations.length;
    for (const anim of data.animations) {
      if (anim.name) animationNames.push(anim.name);
    }
  }

  // Extract texture dimensions from first texture's source (base64 PNG header)
  let textureDimensions: ModelDetail["textureDimensions"] = null;
  if (Array.isArray(data.textures) && data.textures.length > 0) {
    const tex = data.textures[0];
    if (tex.source && typeof tex.source === "string") {
      const base64Match = tex.source.match(/^data:image\/png;base64,(.+)$/);
      if (base64Match) {
        try {
          const pngHeader = Buffer.from(base64Match[1].substring(0, 64), "base64");
          if (pngHeader.length >= 24) {
            const width = pngHeader.readUInt32BE(16);
            const height = pngHeader.readUInt32BE(20);
            if (width > 0 && height > 0 && width < 65536 && height < 65536) {
              textureDimensions = { width, height };
            }
          }
        } catch {
          // Ignore PNG header parsing errors
        }
      }
    }
  }

  const resolution = data.resolution
    ? { width: data.resolution.width || 0, height: data.resolution.height || 0 }
    : null;

  const groups = Array.isArray(data.groups) ? data.groups.length : 0;

  return {
    meta,
    elementCount,
    animationCount,
    animationNames,
    textureDimensions,
    resolution,
    groups,
  };
}

// ─── Config ────────────────────────────────────────────────────────────────

const MDO_SRP_DIR = "/home/z/my-project/MDO-SRP";

const VALID_CATEGORIES = new Set([
  "inborn",
  "deterrent",
  "derived",
  "primitive",
  "adapted",
  "pure",
  "ancient",
  "awakened",
  "feral",
  "crude",
  "infected",
  "hijacked",
  "focused",
  "abomination",
  "projectile",
  "misc",
]);

// ─── Route Handler ─────────────────────────────────────────────────────────

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const category = searchParams.get("category");
    const creature = searchParams.get("creature");

    if (!category || !creature) {
      return NextResponse.json(
        { error: "Missing required parameters: category, creature" },
        { status: 400 }
      );
    }

    if (!VALID_CATEGORIES.has(category)) {
      return NextResponse.json(
        { error: `Invalid category: ${category}` },
        { status: 400 }
      );
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(creature)) {
      return NextResponse.json(
        { error: "Invalid creature name" },
        { status: 400 }
      );
    }

    // Find the .bbmodel file
    const catDir = path.join(MDO_SRP_DIR, category);
    if (!fs.existsSync(catDir)) {
      return NextResponse.json(
        { error: `Category not found: ${category}` },
        { status: 404 }
      );
    }

    const files = fs.readdirSync(catDir);
    let matchedFile: string | null = null;

    if (files.includes(`${creature}.bbmodel`)) {
      matchedFile = `${creature}.bbmodel`;
    } else {
      const lowerTarget = `${creature.toLowerCase()}.bbmodel`;
      const found = files.find((f) => f.toLowerCase() === lowerTarget);
      if (found) matchedFile = found;
    }

    if (!matchedFile) {
      return NextResponse.json(
        { error: `Creature "${creature}" not found in category "${category}"` },
        { status: 404 }
      );
    }

    const filePath = path.join(catDir, matchedFile);

    // Path traversal check
    const resolvedPath = path.resolve(filePath);
    const resolvedDir = path.resolve(MDO_SRP_DIR);
    if (!resolvedPath.startsWith(resolvedDir + path.sep) && resolvedPath !== resolvedDir) {
      return NextResponse.json({ error: "Invalid path" }, { status: 400 });
    }

    // Get file stats
    const stat = fs.statSync(filePath);
    const fileSize = stat.size;
    const isLarge = fileSize >= LARGE_FILE_THRESHOLD;

    // Parse model details (partial for large files, full for small)
    const stats = isLarge
      ? parseBbmodelStatsPartial(filePath)
      : parseBbmodelStatsFull(filePath);

    const response: ModelDetail = {
      id: creature,
      category,
      fileSize,
      fileSizeFormatted: formatBytes(fileSize),
      meta: stats.meta,
      boneCount: stats.groups,
      elementCount: stats.elementCount,
      animationCount: stats.animationCount,
      animationNames: stats.animationNames,
      textureDimensions: stats.textureDimensions,
      resolution: stats.resolution,
      groups: stats.groups,
      largeFile: isLarge,
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("Model detail error:", error);
    return NextResponse.json(
      { error: "Failed to read model details" },
      { status: 500 }
    );
  }
}
