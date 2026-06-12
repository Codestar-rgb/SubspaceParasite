"use client";

import { useState, useEffect, useMemo } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Workflow,
  Code2,
  Layers,
  BarChart3,
  Braces,
  Download,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  Search,
  Box,
  Activity,
  Zap,
  Shield,
  Target,
  GitBranch,
  FileJson,
  Cpu,
  RefreshCw,
  TrendingUp,
  CircleDot,
  type LucideIcon,
} from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────────────────

interface CreatureEntry {
  id: string;
  nameZh: string;
  nameEn: string;
  category: string;
  hasBbmodel: boolean;
}

interface CategoryGroup {
  id: string;
  nameZh: string;
  nameEn: string;
  creatures: CreatureEntry[];
}

interface PipelineSummary {
  models: number;
  animations: number;
  keyframes: number;
  bones: number;
  animatedBones: number;
  totalSizeKB: number;
  failures: number;
  warnings: number;
}

interface CategoryBreakdown {
  id: string;
  name: string;
  models: number;
  animations: number;
  keyframes: number;
  bones: number;
  totalSizeKB: number;
}

interface SizeDistribution {
  label: string;
  count: number;
}

interface PipelineData {
  summary: PipelineSummary;
  categoryBreakdown: CategoryBreakdown[];
  sizeDistribution: SizeDistribution[];
}

// ─── Pipeline Stage Data ────────────────────────────────────────────────────

interface PipelineStage {
  name: string;
  replaces: string;
  improvement: string;
  icon: LucideIcon;
}

const PIPELINE_STAGES: PipelineStage[] = [
  {
    name: "Parse",
    replaces: "Parse (unchanged)",
    improvement: "Structured IR with AxisValue explicit/default tracking",
    icon: FileJson,
  },
  {
    name: "Validate",
    replaces: "Validate (unchanged)",
    improvement: "NaN/Infinity detection, snap-heavy interpolation override",
    icon: Shield,
  },
  {
    name: "SymbolCompile",
    replaces: "CarryForward",
    improvement: "Abolishes carry-forward heuristic — builds SymbolTable instead",
    icon: Cpu,
  },
  {
    name: "PeriodLock",
    replaces: "PeriodAnalysis",
    improvement: "LCM-based consistent loop periods across all bones",
    icon: Target,
  },
  {
    name: "LoopAlign",
    replaces: "LoopAlign (enhanced)",
    improvement: "C0 continuity + synthetic end keyframes for seamless loops",
    icon: RefreshCw,
  },
  {
    name: "SymbolEvaluate",
    replaces: "RotNormalize + Interpolation + SubFrameInsert",
    improvement: "Interpolation selected BEFORE evaluation (fixes chicken-and-egg)",
    icon: Zap,
  },
];

// ─── Key Fix Cards ──────────────────────────────────────────────────────────

interface KeyFix {
  title: string;
  description: string;
  severity: "critical" | "major" | "improvement";
}

const KEY_FIXES: KeyFix[] = [
  {
    title: "Abandon Carry-Forward Interpolation",
    description:
      "Old pipeline used CatmullRom for carry-forward BEFORE interpolation was selected. The SymbolTable approach selects interpolation first, then evaluates — eliminating the chicken-and-egg problem.",
    severity: "critical",
  },
  {
    title: "CatmullRom Overshoot Clamping",
    description:
      "Built directly into AST expressions. When a CatmullRomExpr produces values outside the min/max of its control points, the result is clamped. This prevents spline overshoot artifacts in converted animations.",
    severity: "major",
  },
  {
    title: "LCM Period Locking",
    description:
      "Instead of per-bone period detection (which could give different periods for bones in the same animation), PeriodLock computes the LCM of all detected periods — ensuring consistent loop timing across the entire skeleton.",
    severity: "major",
  },
  {
    title: "Explicit vs Default Tracking",
    description:
      "AxisValue distinguishes between an explicitly-set 0.0 and a missing/unset value. Old pipeline treated missing as 0.0, causing bones to snap to origin when they should carry forward their last value.",
    severity: "critical",
  },
];

// ─── AST Expression Types ───────────────────────────────────────────────────

interface ExprType {
  name: string;
  syntax: string;
  description: string;
  example: string;
}

const AST_EXPR_TYPES: ExprType[] = [
  {
    name: "ConstantExpr",
    syntax: "const(V)",
    description: "Holds a single unchanging value. Used for static poses and carry-forward defaults.",
    example: "const(15.0) → always returns 15.0",
  },
  {
    name: "LinearExpr",
    syntax: "linear(t₀, v₀, t₁, v₁)",
    description: "Two-point linear interpolation. Used for snap-heavy channels where smooth curves would be wrong.",
    example: "linear(0, 0, 1, 90) → at t=0.5 returns 45.0",
  },
  {
    name: "CatmullRomExpr",
    syntax: "catmullrom(P₀, P₁, P₂, P₃, alpha)",
    description: "Cubic Hermite spline through keyframe values with overshoot clamping. Primary curve type for rotation channels.",
    example: "catmullrom(0, 10, 20, 15, 0.5) → smooth curve with min/max clamped to [10, 20]",
  },
  {
    name: "HoldExpr",
    syntax: "hold(V, until_t)",
    description: "Holds a constant value until a specific time, then defers to the next expression. Models step-function animation.",
    example: "hold(5.0, 2.0) → returns 5.0 for t < 2.0",
  },
];

// ─── Formatting Helpers ─────────────────────────────────────────────────────

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

function formatSize(kb: number): string {
  if (kb >= 1024 * 1024) return `${(kb / (1024 * 1024)).toFixed(1)} GB`;
  if (kb >= 1024) return `${(kb / 1024).toFixed(1)} MB`;
  return `${kb.toLocaleString("en-US")} KB`;
}

// ─── Pipeline Tab ───────────────────────────────────────────────────────────

function PipelineTab() {
  return (
    <div className="space-y-6">
      {/* Key Difference Callout */}
      <Card className="border-amber-300 dark:border-amber-700 bg-amber-50/50 dark:bg-amber-950/30">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-amber-800 dark:text-amber-200">
                KEY DIFFERENCE: Interpolation selected BEFORE evaluation
              </p>
              <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                The old pipeline selected interpolation AFTER evaluating carry-forward values — a
                chicken-and-egg problem. The AST Symbol Compiler builds a SymbolTable first,
                selects interpolation per-channel, then evaluates. This eliminates spline artifacts
                caused by wrong interpolation on carry-forward data.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Pipeline Flow */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
          AST Symbol Compiler Pipeline
        </h3>
        <div className="relative">
          {PIPELINE_STAGES.map((stage, i) => {
            const Icon = stage.icon;
            return (
              <div key={stage.name} className="relative">
                {/* Arrow connector */}
                {i > 0 && (
                  <div className="flex justify-center py-1">
                    <div className="flex flex-col items-center">
                      <div className="w-px h-4 bg-border" />
                      <ArrowRight className="h-4 w-4 text-muted-foreground rotate-90" />
                      <div className="w-px h-4 bg-border" />
                    </div>
                  </div>
                )}
                <Card className="hover:shadow-md transition-shadow">
                  <CardContent className="p-4">
                    <div className="flex items-start gap-4">
                      <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-emerald-100 dark:bg-emerald-900 shrink-0">
                        <Icon className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="font-semibold">{stage.name}</h4>
                          <Badge variant="outline" className="text-[10px] font-mono">
                            Stage {i + 1}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          <span className="font-medium">Replaces:</span> {stage.replaces}
                        </p>
                        <p className="text-sm mt-1">
                          <span className="font-medium text-emerald-700 dark:text-emerald-300">
                            Improvement:
                          </span>{" "}
                          {stage.improvement}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── Architecture Tab ───────────────────────────────────────────────────────

function ArchitectureTab() {
  const oldStages = [
    "Parse",
    "Validate",
    "CarryForward (uses CR!)",
    "PeriodAnalysis",
    "LoopAlign",
    "RotNormalize",
    "Interpolation",
    "SubFrameInsert",
  ];

  const newStages = [
    "Parse",
    "Validate",
    "SymbolCompile",
    "PeriodLock",
    "LoopAlign",
    "RotNormalize",
    "SymbolEvaluate",
  ];

  return (
    <div className="space-y-6">
      {/* Pipeline Comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* OLD Pipeline */}
        <Card className="border-rose-200 dark:border-rose-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-rose-500" />
              OLD Pipeline (8 stages)
            </CardTitle>
            <CardDescription>AnimEngineV1 — heuristic-based carry-forward</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            {oldStages.map((stage, i) => (
              <div key={i} className="flex items-center gap-2">
                {i > 0 && <ArrowRight className="h-3 w-3 text-rose-400 shrink-0" />}
                {i === 0 && <div className="w-3 shrink-0" />}
                <span
                  className={`text-sm font-mono ${
                    stage.includes("CR!") ? "text-rose-600 font-semibold" : "text-muted-foreground"
                  }`}
                >
                  {stage}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* NEW Pipeline */}
        <Card className="border-emerald-200 dark:border-emerald-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-emerald-500" />
              NEW Pipeline (7 stages)
            </CardTitle>
            <CardDescription>AST Symbol Compiler — expression-based evaluation</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            {newStages.map((stage, i) => (
              <div key={i} className="flex items-center gap-2">
                {i > 0 && <ArrowRight className="h-3 w-3 text-emerald-400 shrink-0" />}
                {i === 0 && <div className="w-3 shrink-0" />}
                <span
                  className={`text-sm font-mono ${
                    stage === "SymbolCompile" || stage === "SymbolEvaluate"
                      ? "text-emerald-600 font-semibold dark:text-emerald-400"
                      : "text-muted-foreground"
                  }`}
                >
                  {stage}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Key Fixes */}
      <div>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
          Key Architectural Fixes
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {KEY_FIXES.map((fix) => (
            <Card key={fix.title}>
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <div
                    className={`shrink-0 w-2 h-2 rounded-full mt-2 ${
                      fix.severity === "critical"
                        ? "bg-rose-500"
                        : fix.severity === "major"
                        ? "bg-amber-500"
                        : "bg-emerald-500"
                    }`}
                  />
                  <div>
                    <h4 className="font-semibold text-sm">{fix.title}</h4>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      {fix.description}
                    </p>
                    <Badge
                      variant="outline"
                      className={`mt-2 text-[10px] ${
                        fix.severity === "critical"
                          ? "border-rose-300 text-rose-600 dark:border-rose-700 dark:text-rose-400"
                          : fix.severity === "major"
                          ? "border-amber-300 text-amber-600 dark:border-amber-700 dark:text-amber-400"
                          : "border-emerald-300 text-emerald-600 dark:border-emerald-700 dark:text-emerald-400"
                      }`}
                    >
                      {fix.severity}
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Creatures Tab ──────────────────────────────────────────────────────────

function CreaturesTab() {
  const [categories, setCategories] = useState<CategoryGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetch("/api/creatures")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch creatures");
        return res.json();
      })
      .then((data) => {
        setCategories(data.categories || []);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const filteredCategories = useMemo(() => {
    if (!searchQuery.trim()) return categories;
    const q = searchQuery.toLowerCase();
    return categories
      .map((cat) => ({
        ...cat,
        creatures: cat.creatures.filter(
          (c) =>
            c.id.toLowerCase().includes(q) ||
            c.nameZh.includes(q) ||
            c.nameEn.toLowerCase().includes(q)
        ),
      }))
      .filter((cat) => cat.creatures.length > 0);
  }, [categories, searchQuery]);

  const totalCreatures = categories.reduce((sum, c) => sum + c.creatures.length, 0);

  const downloadBbmodel = (category: string, creature: string) => {
    const url = `/api/download?category=${encodeURIComponent(category)}&creature=${encodeURIComponent(creature)}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${creature}.bbmodel`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <Card className="border-rose-200 dark:border-rose-800">
        <CardContent className="p-4 text-center text-rose-600 dark:text-rose-400">
          Failed to load creatures: {error}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">Creature Models</h3>
          <p className="text-sm text-muted-foreground">
            {totalCreatures} creatures across {categories.length} categories
          </p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search creatures..."
            className="pl-8"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Category Accordion */}
      <Accordion type="multiple" defaultValue={["inborn", "deterrent", "derived"]} className="space-y-2">
        {filteredCategories.map((cat) => (
          <AccordionItem key={cat.id} value={cat.id}>
            <AccordionTrigger className="hover:no-underline py-3">
              <div className="flex items-center gap-3">
                <Badge variant="secondary" className="shrink-0">
                  {cat.creatures.length}
                </Badge>
                <span className="font-medium text-sm">
                  {cat.nameEn}
                </span>
                <span className="text-xs text-muted-foreground">
                  ({cat.nameZh})
                </span>
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 pt-1">
                {cat.creatures.map((creature) => (
                  <div
                    key={creature.id}
                    className="flex items-center justify-between p-2.5 rounded-lg border bg-muted/30 hover:bg-muted/50 transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{creature.nameEn}</p>
                      <p className="text-xs text-muted-foreground">
                        {creature.nameZh} · <code className="font-mono text-[10px]">{creature.id}</code>
                      </p>
                    </div>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            size="sm"
                            variant="outline"
                            className="shrink-0 ml-2"
                            onClick={() => downloadBbmodel(creature.category, creature.id)}
                          >
                            <Download className="h-3.5 w-3.5" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p>Download {creature.id}.bbmodel</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                ))}
              </div>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>

      {filteredCategories.length === 0 && searchQuery && (
        <div className="text-center py-8 text-muted-foreground">
          No creatures found matching &quot;{searchQuery}&quot;
        </div>
      )}
    </div>
  );
}

// ─── Stats Tab ──────────────────────────────────────────────────────────────

function StatsTab() {
  const [data, setData] = useState<PipelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/pipeline")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch stats");
        return res.json();
      })
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <Card className="border-rose-200 dark:border-rose-800">
        <CardContent className="p-4 text-center text-rose-600 dark:text-rose-400">
          Failed to load stats: {error}
        </CardContent>
      </Card>
    );
  }

  const { summary, categoryBreakdown, sizeDistribution } = data;

  const metrics = [
    { label: "Models Converted", value: formatNumber(summary.models), icon: Box, color: "text-emerald-600" },
    { label: "Animations", value: formatNumber(summary.animations), icon: Activity, color: "text-amber-600" },
    { label: "Keyframes", value: formatNumber(summary.keyframes), icon: Zap, color: "text-orange-600" },
    { label: "Animated Bones", value: formatNumber(summary.animatedBones), icon: GitBranch, color: "text-teal-600" },
    { label: "Conversion Failures", value: formatNumber(summary.failures), icon: CheckCircle2, color: "text-emerald-600" },
    { label: "Warnings", value: formatNumber(summary.warnings), icon: CheckCircle2, color: "text-emerald-600" },
  ];

  const maxCategoryModels = Math.max(...categoryBreakdown.map((c) => c.models));

  return (
    <div className="space-y-6">
      {/* Key Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {metrics.map((m) => {
          const Icon = m.icon;
          return (
            <Card key={m.label}>
              <CardContent className="p-4 text-center">
                <Icon className={`h-5 w-5 mx-auto mb-2 ${m.color}`} />
                <p className="text-2xl font-bold">{m.value}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">{m.label}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Total Size */}
      <Card>
        <CardContent className="p-4 flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">Total Output Size</p>
            <p className="text-xl font-bold">{formatSize(summary.totalSizeKB)}</p>
          </div>
          <Badge variant="outline" className="text-xs">
            {formatNumber(summary.bones)} total bones
          </Badge>
        </CardContent>
      </Card>

      {/* Category Breakdown */}
      <div>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
          Category Breakdown
        </h3>
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-3 font-medium text-muted-foreground">Category</th>
                    <th className="text-right p-3 font-medium text-muted-foreground">Models</th>
                    <th className="text-right p-3 font-medium text-muted-foreground hidden sm:table-cell">Animations</th>
                    <th className="text-right p-3 font-medium text-muted-foreground hidden md:table-cell">Keyframes</th>
                    <th className="text-right p-3 font-medium text-muted-foreground hidden lg:table-cell">Size</th>
                    <th className="p-3 font-medium text-muted-foreground hidden sm:table-cell">Distribution</th>
                  </tr>
                </thead>
                <tbody>
                  {categoryBreakdown.map((cat) => (
                    <tr key={cat.id} className="border-b last:border-0 hover:bg-muted/50 transition-colors">
                      <td className="p-3 font-medium">{cat.name}</td>
                      <td className="p-3 text-right font-mono">{cat.models}</td>
                      <td className="p-3 text-right font-mono hidden sm:table-cell">{cat.animations}</td>
                      <td className="p-3 text-right font-mono hidden md:table-cell">{formatNumber(cat.keyframes)}</td>
                      <td className="p-3 text-right font-mono hidden lg:table-cell">{formatSize(cat.totalSizeKB)}</td>
                      <td className="p-3 hidden sm:table-cell">
                        <div className="w-full max-w-[120px]">
                          <Progress value={(cat.models / maxCategoryModels) * 100} className="h-2" />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* File Size Distribution */}
      <div>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
          File Size Distribution
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {sizeDistribution.map((bucket) => (
            <Card key={bucket.label}>
              <CardContent className="p-3 text-center">
                <p className="text-lg font-bold">{bucket.count}</p>
                <p className="text-[11px] text-muted-foreground">{bucket.label}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── AST Tab ────────────────────────────────────────────────────────────────

function AstTab() {
  return (
    <div className="space-y-6">
      {/* Overview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Braces className="h-5 w-5 text-emerald-600" />
            AST Symbol Compiler Architecture
          </CardTitle>
          <CardDescription>
            The Symbol Compiler replaces the heuristic-based carry-forward system with a formal
            Abstract Syntax Tree representation of animation expressions.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm leading-relaxed">
            Instead of immediately evaluating keyframe values during carry-forward, the Symbol
            Compiler builds a <strong>SymbolTable</strong> — a mapping from each bone/channel/axis
            to an AST expression tree. Interpolation is selected per-channel BEFORE evaluation,
            eliminating the chicken-and-egg problem where CatmullRom carry-forward values were
            computed before the correct interpolation type was known.
          </p>
        </CardContent>
      </Card>

      {/* Expression Types */}
      <div>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
          Expression Types
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {AST_EXPR_TYPES.map((expr) => (
            <Card key={expr.name}>
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-emerald-700 dark:text-emerald-300">
                    {expr.name}
                  </h4>
                  <code className="text-xs bg-muted px-2 py-0.5 rounded font-mono">
                    {expr.syntax}
                  </code>
                </div>
                <p className="text-sm text-muted-foreground">{expr.description}</p>
                <div className="p-2 rounded bg-muted/50 border text-xs font-mono">
                  {expr.example}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* SymbolTable Example */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">SymbolTable Structure</CardTitle>
          <CardDescription>
            How the SymbolTable maps bone channels to AST expressions
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="p-4 rounded-lg bg-muted/50 border font-mono text-xs leading-relaxed overflow-x-auto">
            <pre>{`SymbolTable {
  "root" → {
    "rotation" → {
      "x": CatmullRomExpr([0.0, 5.0, 10.0, 5.0], clamp=true),
      "y": ConstantExpr(0.0),         // explicit 0.0
      "z": HoldExpr(0.0, until=2.0),  // carry-forward default
    }
  },
  "body" → {
    "rotation" → {
      "x": LinearExpr(0, 0, 1, 15.0), // snap-heavy override
      "y": CatmullRomExpr([...], clamp=true),
      "z": ConstantExpr(0.0),          // explicit 0.0 (NOT missing!)
    }
  },
  "wing_left" → {
    "rotation" → {
      "x": CatmullRomExpr([0, -20, 0, -20], clamp=true),
      "y": ConstantExpr(0.0),
      "z": ConstantExpr(0.0),
    }
  }
}`}</pre>
          </div>
        </CardContent>
      </Card>

      {/* Interpolation Selection Rules */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Interpolation Selection Rules</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <div className="flex items-start gap-3 p-3 rounded-lg border bg-muted/30">
              <div className="w-6 h-6 rounded-full bg-emerald-100 dark:bg-emerald-900 flex items-center justify-center shrink-0">
                <span className="text-xs font-bold text-emerald-600">1</span>
              </div>
              <div>
                <p className="text-sm font-medium">Default: CatmullRom for rotation channels</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Smooth cubic Hermite spline for all rotation axes unless overridden
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3 p-3 rounded-lg border bg-muted/30">
              <div className="w-6 h-6 rounded-full bg-amber-100 dark:bg-amber-900 flex items-center justify-center shrink-0">
                <span className="text-xs font-bold text-amber-600">2</span>
              </div>
              <div>
                <p className="text-sm font-medium">Snap-heavy override → Linear</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  If &gt;50% of consecutive keyframe pairs have delta &gt; 30°, the channel is
                  classified as snap-heavy and uses linear interpolation
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3 p-3 rounded-lg border bg-muted/30">
              <div className="w-6 h-6 rounded-full bg-rose-100 dark:bg-rose-900 flex items-center justify-center shrink-0">
                <span className="text-xs font-bold text-rose-600">3</span>
              </div>
              <div>
                <p className="text-sm font-medium">Position/Scale → Linear</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Position and scale channels always use linear interpolation
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3 p-3 rounded-lg border bg-muted/30">
              <div className="w-6 h-6 rounded-full bg-teal-100 dark:bg-teal-900 flex items-center justify-center shrink-0">
                <span className="text-xs font-bold text-teal-600">4</span>
              </div>
              <div>
                <p className="text-sm font-medium">Single keyframe → Constant</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Channels with only one keyframe value become ConstantExpr
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Overshoot Clamping Formula */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Shield className="h-5 w-5 text-amber-600" />
            CatmullRom Overshoot Clamping
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            When CatmullRom interpolation produces values outside the range of its control points,
            the result is clamped to prevent spline overshoot artifacts:
          </p>
          <div className="p-4 rounded-lg bg-muted/50 border font-mono text-sm text-center">
            <p>result = catmullrom(P₀, P₁, P₂, P₃, t)</p>
            <p className="mt-1">clamped = clamp(result, min(P₁, P₂), max(P₁, P₂))</p>
          </div>
          <p className="text-xs text-muted-foreground">
            The clamp bounds use the inner control points P₁ and P₂ (the interpolated segment
            endpoints), not the tangent control points P₀ and P₃. This preserves the smooth curve
            shape while eliminating overshoot beyond the keyframe value range.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Download Tab ───────────────────────────────────────────────────────────

function DownloadTab() {
  const [categories, setCategories] = useState<CategoryGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/creatures")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch creatures");
        return res.json();
      })
      .then((data) => {
        setCategories(data.categories || []);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const downloadBbmodel = (category: string, creature: string) => {
    const url = `/api/download?category=${encodeURIComponent(category)}&creature=${encodeURIComponent(creature)}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${creature}.bbmodel`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const downloadAllForCategory = (cat: CategoryGroup) => {
    cat.creatures.forEach((creature, i) => {
      setTimeout(() => {
        downloadBbmodel(creature.category, creature.id);
      }, i * 300);
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <Card className="border-rose-200 dark:border-rose-800">
        <CardContent className="p-4 text-center text-rose-600 dark:text-rose-400">
          Failed to load downloads: {error}
        </CardContent>
      </Card>
    );
  }

  const totalCreatures = categories.reduce((sum, c) => sum + c.creatures.length, 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Download Center</h3>
          <p className="text-sm text-muted-foreground">
            {totalCreatures} Blockbench models (.bbmodel) ready for download
          </p>
        </div>
        <Badge variant="outline" className="text-xs">
          .bbmodel format
        </Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {categories.map((cat) => (
          <Card key={cat.id}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm">{cat.nameEn}</CardTitle>
                  <CardDescription className="text-xs">
                    {cat.nameZh} · {cat.creatures.length} models
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs gap-1"
                  onClick={() => downloadAllForCategory(cat)}
                >
                  <Download className="h-3 w-3" />
                  All
                </Button>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <div className="max-h-48 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
                {cat.creatures.map((creature) => (
                  <div
                    key={creature.id}
                    className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-muted/50 transition-colors"
                  >
                    <span className="text-sm truncate">
                      {creature.nameEn}{" "}
                      <span className="text-xs text-muted-foreground">({creature.id})</span>
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0 shrink-0"
                      onClick={() => downloadBbmodel(creature.category, creature.id)}
                    >
                      <Download className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────────────────

export default function MDOSRPDashboard() {
  const [activeTab, setActiveTab] = useState("pipeline");

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
        <div className="max-w-6xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-emerald-600 text-white shrink-0">
              <Workflow className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h1 className="text-xl font-bold tracking-tight truncate">
                MDO-SRP — Symbol Resolution Pipeline
              </h1>
              <p className="text-xs text-muted-foreground truncate">
                AST Symbol Compiler Architecture · 168 Models · 0 Errors · v2.0
              </p>
            </div>
            <div className="hidden sm:flex items-center gap-2 ml-auto">
              <Badge className="gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300 border-0">
                <CheckCircle2 className="h-3 w-3" /> 168 Converted
              </Badge>
              <Badge className="gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300 border-0">
                <CheckCircle2 className="h-3 w-3" /> 0 Failures
              </Badge>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6 sm:px-6 lg:px-8">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="grid w-full grid-cols-3 sm:grid-cols-6 max-w-full">
            <TabsTrigger value="pipeline" className="gap-1 text-xs sm:text-sm">
              <Workflow className="h-3.5 w-3.5 hidden sm:block" />
              Pipeline
            </TabsTrigger>
            <TabsTrigger value="architecture" className="gap-1 text-xs sm:text-sm">
              <Code2 className="h-3.5 w-3.5 hidden sm:block" />
              Arch
            </TabsTrigger>
            <TabsTrigger value="creatures" className="gap-1 text-xs sm:text-sm">
              <Layers className="h-3.5 w-3.5 hidden sm:block" />
              Creatures
            </TabsTrigger>
            <TabsTrigger value="stats" className="gap-1 text-xs sm:text-sm">
              <BarChart3 className="h-3.5 w-3.5 hidden sm:block" />
              Stats
            </TabsTrigger>
            <TabsTrigger value="ast" className="gap-1 text-xs sm:text-sm">
              <Braces className="h-3.5 w-3.5 hidden sm:block" />
              AST
            </TabsTrigger>
            <TabsTrigger value="download" className="gap-1 text-xs sm:text-sm">
              <Download className="h-3.5 w-3.5 hidden sm:block" />
              Download
            </TabsTrigger>
          </TabsList>

          <TabsContent value="pipeline">
            <PipelineTab />
          </TabsContent>

          <TabsContent value="architecture">
            <ArchitectureTab />
          </TabsContent>

          <TabsContent value="creatures">
            <CreaturesTab />
          </TabsContent>

          <TabsContent value="stats">
            <StatsTab />
          </TabsContent>

          <TabsContent value="ast">
            <AstTab />
          </TabsContent>

          <TabsContent value="download">
            <DownloadTab />
          </TabsContent>
        </Tabs>
      </main>

      {/* Footer */}
      <footer className="mt-auto border-t bg-card">
        <div className="max-w-6xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <CircleDot className="h-3 w-3 text-emerald-500" />
              <span>MDO-SRP v2.0 — Model Data Optimization via Symbol Resolution Pipeline</span>
            </div>
            <div className="flex items-center gap-3">
              <span>168 Models</span>
              <Separator orientation="vertical" className="h-3" />
              <span>310 Animations</span>
              <Separator orientation="vertical" className="h-3" />
              <span>1.35M Keyframes</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
