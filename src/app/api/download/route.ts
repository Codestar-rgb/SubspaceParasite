import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

// ─── Types ──────────────────────────────────────────────────────────────────

type FileType = "bbmodel" | "geo" | "anim" | "texture";

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

const VALID_TYPES = new Set<string>(["bbmodel", "geo", "anim", "texture"]);

const CONTENT_TYPES: Record<string, string> = {
  bbmodel: "application/json",
  geo: "application/json",
  anim: "application/json",
  texture: "image/png",
};

// ─── Route Handler ─────────────────────────────────────────────────────────

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const category = searchParams.get("category");
    const creature = searchParams.get("creature");
    const type = (searchParams.get("type") || "bbmodel") as FileType;

    // Validate required params
    if (!category || !creature) {
      return NextResponse.json(
        { error: "Missing required parameters: category, creature" },
        { status: 400 }
      );
    }

    // Validate category
    if (!VALID_CATEGORIES.has(category)) {
      return NextResponse.json(
        { error: `Invalid category: ${category}` },
        { status: 400 }
      );
    }

    // Validate creature name (alphanumeric, underscore, hyphen only)
    if (!/^[a-zA-Z0-9_-]+$/.test(creature)) {
      return NextResponse.json(
        { error: "Invalid creature name" },
        { status: 400 }
      );
    }

    // Validate type
    if (!VALID_TYPES.has(type)) {
      return NextResponse.json(
        { error: `Invalid type: ${type}. Must be one of: bbmodel, geo, anim, texture` },
        { status: 400 }
      );
    }

    // Only bbmodel files are available in MDO-SRP
    if (type !== "bbmodel") {
      return NextResponse.json(
        {
          error: `File type "${type}" is not available. Only .bbmodel files exist in MDO-SRP.`,
          suggestion: 'Use type="bbmodel" to download the Blockbench model file.',
        },
        { status: 404 }
      );
    }

    // Resolve the category directory
    const catDir = path.join(MDO_SRP_DIR, category);
    if (!fs.existsSync(catDir)) {
      return NextResponse.json(
        { error: `Category directory not found: ${category}` },
        { status: 404 }
      );
    }

    // Find the .bbmodel file (exact match, then case-insensitive)
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

    // Build file path and verify it stays within MDO-SRP (path traversal check)
    const filePath = path.join(catDir, matchedFile);
    const resolvedPath = path.resolve(filePath);
    const resolvedDir = path.resolve(MDO_SRP_DIR);
    if (!resolvedPath.startsWith(resolvedDir + path.sep) && resolvedPath !== resolvedDir) {
      return NextResponse.json(
        { error: "Invalid path" },
        { status: 400 }
      );
    }

    // Read and serve the file
    const content = fs.readFileSync(filePath);
    const contentType = CONTENT_TYPES[type] || "application/octet-stream";

    return new NextResponse(content, {
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="${matchedFile}"`,
        "Cache-Control": "public, max-age=3600",
        "Content-Length": content.length.toString(),
      },
    });
  } catch (error) {
    console.error("Download error:", error);
    return NextResponse.json(
      { error: "Failed to serve file" },
      { status: 500 }
    );
  }
}
