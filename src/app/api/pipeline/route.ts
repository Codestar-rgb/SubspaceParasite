import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

// ─── Types ──────────────────────────────────────────────────────────────────

interface CategoryStats {
  id: string;
  modelCount: number;
  totalSize: number;
}

interface PipelineStatsResponse {
  totalModels: number;
  totalCategories: number;
  totalSize: number;
  sizeFormatted: string;
  categories: CategoryStats[];
  sourceFormat: string;
  outputFormat: string;
  converterVersion: string;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

// ─── Config ────────────────────────────────────────────────────────────────

const MDO_SRP_DIR = "/home/z/my-project/MDO-SRP";

// ─── Route Handler ─────────────────────────────────────────────────────────

export async function GET() {
  try {
    if (!fs.existsSync(MDO_SRP_DIR)) {
      return NextResponse.json(
        { error: "MDO-SRP directory not found" },
        { status: 500 }
      );
    }

    const categories: CategoryStats[] = [];
    let totalModels = 0;
    let totalSize = 0;

    const entries = fs.readdirSync(MDO_SRP_DIR, { withFileTypes: true });

    for (const entry of entries) {
      if (!entry.isDirectory()) continue;

      const catDir = path.join(MDO_SRP_DIR, entry.name);
      const files = fs.readdirSync(catDir);
      const bbmodelFiles = files.filter((f) => f.endsWith(".bbmodel"));

      let catSize = 0;
      for (const f of bbmodelFiles) {
        const stat = fs.statSync(path.join(catDir, f));
        catSize += stat.size;
      }

      totalModels += bbmodelFiles.length;
      totalSize += catSize;

      categories.push({
        id: entry.name,
        modelCount: bbmodelFiles.length,
        totalSize: catSize,
      });
    }

    // Sort categories by model count descending
    categories.sort((a, b) => b.modelCount - a.modelCount);

    const response: PipelineStatsResponse = {
      totalModels,
      totalCategories: categories.length,
      totalSize,
      sizeFormatted: formatBytes(totalSize),
      categories,
      sourceFormat: "GeckoLib geo.json + animation.json + PNG",
      outputFormat: "Blockbench .bbmodel",
      converterVersion: "super-converter v2 (AST Symbol Compiler)",
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("Failed to compute pipeline stats:", error);
    return NextResponse.json(
      { error: "Failed to compute pipeline stats" },
      { status: 500 }
    );
  }
}
