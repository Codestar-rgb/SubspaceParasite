import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const OUTPUT_DIR = path.join(process.cwd(), "db", "output");

// Valid categories to prevent path traversal
const VALID_CATEGORIES = [
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
];

const VALID_EXTENSIONS = [".geo.json", ".animation.json", ".png"];

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const category = searchParams.get("category");
  const creature = searchParams.get("creature");
  const type = searchParams.get("type"); // "geo", "animation", "texture"

  if (!category || !creature || !type) {
    return NextResponse.json(
      { error: "Missing parameters: category, creature, type" },
      { status: 400 }
    );
  }

  if (!VALID_CATEGORIES.includes(category)) {
    return NextResponse.json({ error: "Invalid category" }, { status: 400 });
  }

  // Sanitize creature name - only allow alphanumeric + specific chars
  if (!/^[a-zA-Z0-9_-]+$/.test(creature)) {
    return NextResponse.json({ error: "Invalid creature name" }, { status: 400 });
  }

  let filename: string;
  let contentType: string;

  switch (type) {
    case "geo":
      filename = `${creature}.geo.json`;
      contentType = "application/json";
      break;
    case "animation":
      filename = `${creature}.animation.json`;
      contentType = "application/json";
      break;
    case "texture":
      filename = `${creature}.png`;
      contentType = "image/png";
      break;
    default:
      return NextResponse.json({ error: "Invalid type" }, { status: 400 });
  }

  const filePath = path.join(OUTPUT_DIR, category, filename);

  // Verify the resolved path is still within OUTPUT_DIR (path traversal check)
  const resolvedPath = path.resolve(filePath);
  const resolvedOutputDir = path.resolve(OUTPUT_DIR);
  if (!resolvedPath.startsWith(resolvedOutputDir)) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  if (!fs.existsSync(filePath)) {
    return NextResponse.json({ error: "File not found" }, { status: 404 });
  }

  try {
    const content = fs.readFileSync(filePath);
    return new NextResponse(content, {
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control": "public, max-age=3600",
      },
    });
  } catch {
    return NextResponse.json({ error: "Failed to read file" }, { status: 500 });
  }
}
