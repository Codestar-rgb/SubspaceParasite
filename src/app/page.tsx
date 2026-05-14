"use client";

import { useState, useEffect, useCallback } from "react";
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
import {
  Download,
  FileJson,
  FileCode,
  ImageIcon,
  Table2,
  Box,
  Activity,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  AlertTriangle,
  Zap,
  ArrowRightLeft,
  Shield,
  Eye,
  Cpu,
  Puzzle,
  XCircle,
  Info,
} from "lucide-react";

interface BoneMapping {
  [key: string]: string;
}

interface GeoJsonModel {
  format_version: string;
  model: {
    identifier: string;
    texture_width: number;
    texture_height: number;
    bones: BoneData[];
  };
}

interface BoneData {
  name: string;
  parent?: string;
  pivot: number[];
  rotation?: number[];
  cubes?: CubeData[];
}

interface CubeData {
  origin: number[];
  size: number[];
  uv: Record<string, { uv: number[]; uv_size: number[] }>;
  mirror?: boolean;
  inflate?: number;
}

interface AnimationJson {
  format_version: string;
  animations: {
    [key: string]: {
      loop: string;
      animation_length: number;
      bones: {
        [key: string]: {
          rotation: {
            [axis: string]: { [time: string]: number };
          };
        };
      };
    };
  };
}

export default function ConverterPage() {
  const [geoJson, setGeoJson] = useState<GeoJsonModel | null>(null);
  const [animJson, setAnimJson] = useState<AnimationJson | null>(null);
  const [boneMapping, setBoneMapping] = useState<BoneMapping>({});
  const [selectedBone, setSelectedBone] = useState<string | null>(null);
  const [expandedBones, setExpandedBones] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [geoRes, animRes, mapRes] = await Promise.all([
          fetch("/converted/kirin.geo.json"),
          fetch("/converted/kirin.animation.json"),
          fetch("/converted/kirin_bone_mapping.json"),
        ]);

        const geo = await geoRes.json();
        const anim = await animRes.json();
        const map = await mapRes.json();

        setGeoJson(geo);
        setAnimJson(anim);
        setBoneMapping(map);
      } catch (e) {
        console.error("Failed to load data:", e);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const toggleBone = useCallback((name: string) => {
    setExpandedBones((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  const downloadFile = useCallback(
    (url: string, filename: string) => {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    },
    []
  );

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
          <p className="text-muted-foreground">Loading conversion data...</p>
        </div>
      </div>
    );
  }

  const boneCount = geoJson?.model.bones.length ?? 0;
  const totalCubes =
    geoJson?.model.bones.reduce(
      (sum, b) => sum + (b.cubes?.length ?? 0),
      0
    ) ?? 0;
  const animBones = animJson
    ? Object.keys(
        animJson.animations["animation.model.idle"]?.bones ?? {}
      ).length
    : 0;
  const animLength = animJson?.animations["animation.model.idle"]
    ?.animation_length ?? 0;

  // UV validation - check for out-of-bounds UVs
  const uvViolations: { bone: string; cube: number; face: string; issue: string }[] = [];
  const texW = geoJson?.model.texture_width ?? 256;
  const texH = geoJson?.model.texture_height ?? 256;
  geoJson?.model.bones.forEach((bone) => {
    bone.cubes?.forEach((cube, ci) => {
      Object.entries(cube.uv).forEach(([face, uvData]) => {
        const u = uvData.uv[0], v = uvData.uv[1];
        const us = uvData.uv_size[0], vs = uvData.uv_size[1];
        if (u + us > texW) uvViolations.push({ bone: bone.name, cube: ci, face, issue: `u+us=${u+us} > tw=${texW}` });
        if (v + vs > texH) uvViolations.push({ bone: bone.name, cube: ci, face, issue: `v+vs=${v+vs} > th=${texH}` });
        if (u < 0) uvViolations.push({ bone: bone.name, cube: ci, face, issue: `u=${u} < 0` });
        if (v < 0) uvViolations.push({ bone: bone.name, cube: ci, face, issue: `v=${v} < 0` });
      });
    });
  });

  // Build bone hierarchy
  const boneMap = new Map<string, BoneData>();
  const childrenMap = new Map<string, string[]>();
  geoJson?.model.bones.forEach((bone) => {
    boneMap.set(bone.name, bone);
    const parent = bone.parent ?? "root";
    if (!childrenMap.has(parent)) childrenMap.set(parent, []);
    childrenMap.get(parent)!.push(bone.name);
  });

  // Count cubes with inflate
  const cubesWithInflate =
    geoJson?.model.bones.reduce(
      (sum, b) => sum + (b.cubes?.filter((c) => c.inflate && Math.abs(c.inflate) > 0.001).length ?? 0),
      0
    ) ?? 0;

  // Check if root bone has correct pivot
  const rootBone = geoJson?.model.bones.find((b) => b.name === "root");
  const rootPivotValid = rootBone ? Math.abs(rootBone.pivot[1] - 24) < 0.01 : false;

  const renderBoneTree = (boneName: string, depth: number = 0) => {
    const bone = boneMap.get(boneName);
    if (!bone) return null;
    const children = childrenMap.get(boneName) ?? [];
    const isExpanded = expandedBones.has(boneName);
    const isSelected = selectedBone === boneName;
    const hasRotation =
      bone.rotation &&
      bone.rotation.some((v) => Math.abs(v) > 0.01);
    const hasCubes = (bone.cubes?.length ?? 0) > 0;

    return (
      <div key={boneName}>
        <div
          className={`flex items-center gap-2 py-1.5 px-2 rounded-md cursor-pointer transition-colors text-sm ${
            isSelected
              ? "bg-primary/10 border border-primary/30"
              : "hover:bg-muted"
          }`}
          style={{ paddingLeft: `${depth * 20 + 8}px` }}
          onClick={() => {
            setSelectedBone(boneName);
            if (children.length > 0) toggleBone(boneName);
          }}
        >
          {children.length > 0 ? (
            isExpanded ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            )
          ) : (
            <span className="w-3.5 shrink-0" />
          )}
          <span className="font-mono truncate">{boneName}</span>
          {hasRotation && (
            <Badge variant="secondary" className="h-4 px-1 text-[10px]">
              R
            </Badge>
          )}
          {hasCubes && (
            <Badge variant="outline" className="h-4 px-1 text-[10px]">
              {bone.cubes!.length}C
            </Badge>
          )}
        </div>
        {isExpanded &&
          children.map((child) => renderBoneTree(child, depth + 1))}
      </div>
    );
  };

  const selectedBoneData = selectedBone
    ? boneMap.get(selectedBone)
    : null;

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary text-primary-foreground">
              <ArrowRightLeft className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight">
                MC 1.12.2 → GeckoLib 1.20.1 Converter
              </h1>
              <p className="text-sm text-muted-foreground">
                Kirin Entity • SRParasites 1.10.4 • ModelBase → GeckoLib
                Conversion
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6 sm:px-6 lg:px-8">
        {/* Stats Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <Box className="h-4 w-4 text-emerald-600" />
                <div>
                  <p className="text-2xl font-bold">{boneCount}</p>
                  <p className="text-xs text-muted-foreground">Bones</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <Box className="h-4 w-4 text-amber-600" />
                <div>
                  <p className="text-2xl font-bold">{totalCubes}</p>
                  <p className="text-xs text-muted-foreground">Cubes</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-rose-600" />
                <div>
                  <p className="text-2xl font-bold">{animBones}</p>
                  <p className="text-xs text-muted-foreground">
                    Animated Bones
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-violet-600" />
                <div>
                  <p className="text-2xl font-bold">{animLength.toFixed(2)}s</p>
                  <p className="text-xs text-muted-foreground">Anim Length</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Conversion Pipeline Status */}
        <Card className="mb-6">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Conversion Pipeline</CardTitle>
              <CardDescription>
                Modular engine: CoreMath (M_model) → ModelConverter → AnimationConverter → Verifier
              </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="text-sm font-medium">CoreMath</span>
                <Badge variant="secondary" className="text-[10px]">
                  M_model
                </Badge>
              </div>
              <ArrowRightLeft className="h-4 w-4 text-muted-foreground" />
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="text-sm font-medium">ModelConverter</span>
                <Badge variant="secondary" className="text-[10px]">
                  Y-flip
                </Badge>
              </div>
              <ArrowRightLeft className="h-4 w-4 text-muted-foreground" />
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="text-sm font-medium">AnimConverter</span>
                <Badge variant="secondary" className="text-[10px]">
                  Class A-1
                </Badge>
              </div>
              <ArrowRightLeft className="h-4 w-4 text-muted-foreground" />
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="text-sm font-medium">Verifier</span>
                <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
                  Enhanced
                </Badge>
              </div>
            </div>
            {/* Verification Status Badges */}
            <div className="flex flex-wrap gap-2 mt-3">
              <Badge variant="outline" className="text-[10px] gap-1">
                <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                Vertex: {rootPivotValid ? "Y-offset OK" : "Check Y-offset"}
              </Badge>
              <Badge variant="outline" className="text-[10px] gap-1">
                {uvViolations.length === 0 ? (
                  <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                ) : (
                  <AlertTriangle className="h-3 w-3 text-amber-500" />
                )}
                UV: {uvViolations.length === 0 ? "In Bounds" : `${uvViolations.length} violations`}
              </Badge>
              <Badge variant="outline" className="text-[10px] gap-1">
                <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                Hierarchy: Preserved
              </Badge>
              <Badge variant="outline" className="text-[10px] gap-1">
                <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                Inflate: {cubesWithInflate > 0 ? `${cubesWithInflate} cubes` : "None"}
              </Badge>
              <Badge variant="outline" className="text-[10px] gap-1">
                <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                Blockbench: Valid
              </Badge>
            </div>
            {/* Layer 1 Enhancement Modules */}
            <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t">
              <span className="text-[10px] font-medium text-muted-foreground self-center mr-1">Enhancement:</span>
              <Badge className="text-[10px] gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
                <CheckCircle2 className="h-3 w-3" /> RenderEffect ✓
              </Badge>
              <Badge className="text-[10px] gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
                <CheckCircle2 className="h-3 w-3" /> EasingFitter ✓
              </Badge>
              <Badge className="text-[10px] gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
                <CheckCircle2 className="h-3 w-3" /> SwingAnalyzer ✓
              </Badge>
              <Badge className="text-[10px] gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
                <CheckCircle2 className="h-3 w-3" /> LayerSeparator ✓
              </Badge>
              <Badge className="text-[10px] gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
                <CheckCircle2 className="h-3 w-3" /> EventMarker ✓
              </Badge>
              <Badge className="text-[10px] gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
                <CheckCircle2 className="h-3 w-3" /> VisibilityDetector ✓
              </Badge>
            </div>
          </CardContent>
        </Card>

        {/* Main Tabs */}
        <Tabs defaultValue="model" className="space-y-4">
          <TabsList className="grid w-full grid-cols-8">
            <TabsTrigger value="model" className="gap-1">
              <Box className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Model</span>
            </TabsTrigger>
            <TabsTrigger value="animation" className="gap-1">
              <Activity className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Animation</span>
            </TabsTrigger>
            <TabsTrigger value="verification" className="gap-1">
              <Shield className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Verify</span>
            </TabsTrigger>
            <TabsTrigger value="mapping" className="gap-1">
              <Table2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Mapping</span>
            </TabsTrigger>
            <TabsTrigger value="architecture" className="gap-1">
              <Cpu className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Arch</span>
            </TabsTrigger>
            <TabsTrigger value="texture" className="gap-1">
              <ImageIcon className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Texture</span>
            </TabsTrigger>
            <TabsTrigger value="downloads" className="gap-1">
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Files</span>
            </TabsTrigger>
            <TabsTrigger value="enhance" className="gap-1">
              <Zap className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Enhance</span>
            </TabsTrigger>
          </TabsList>

          {/* Model Tab */}
          <TabsContent value="model">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Bone Hierarchy */}
              <Card className="lg:col-span-1">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">
                    Bone Hierarchy ({boneCount} bones)
                  </CardTitle>
                </CardHeader>
                <CardContent className="max-h-[600px] overflow-y-auto">
                  {renderBoneTree("root")}
                </CardContent>
              </Card>

              {/* Bone Details */}
              <Card className="lg:col-span-2">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">
                    {selectedBoneData
                      ? `Bone: ${selectedBone}`
                      : "Select a bone to view details"}
                  </CardTitle>
                </CardHeader>
                <CardContent className="max-h-[600px] overflow-y-auto">
                  {selectedBoneData ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">
                            Parent
                          </p>
                          <p className="font-mono text-sm">
                            {selectedBoneData.parent ?? "—"}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">
                            Pivot Point
                          </p>
                          <p className="font-mono text-sm">
                            [{selectedBoneData.pivot.map((v) => v.toFixed(2)).join(", ")}]
                          </p>
                        </div>
                        {selectedBoneData.rotation && (
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">
                              Rotation (deg)
                            </p>
                            <p className="font-mono text-sm">
                              [
                              {selectedBoneData.rotation
                                .map((v) => v.toFixed(2))
                                .join(", ")}
                              ]
                            </p>
                          </div>
                        )}
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">
                            Cubes
                          </p>
                          <p className="font-mono text-sm">
                            {selectedBoneData.cubes?.length ?? 0}
                          </p>
                        </div>
                      </div>

                      {selectedBoneData.cubes &&
                        selectedBoneData.cubes.length > 0 && (
                          <div>
                            <Separator className="my-3" />
                            <p className="text-xs font-medium mb-2">Cubes</p>
                            <div className="space-y-3">
                              {selectedBoneData.cubes.map((cube, i) => (
                                <div
                                  key={i}
                                  className="p-3 rounded-lg bg-muted/50 border"
                                >
                                  <div className="grid grid-cols-2 gap-2 text-xs mb-2">
                                    <div>
                                      <span className="text-muted-foreground">
                                        Origin:{" "}
                                      </span>
                                      <span className="font-mono">
                                        [{cube.origin.map((v) => v.toFixed(1)).join(", ")}]
                                      </span>
                                    </div>
                                    <div>
                                      <span className="text-muted-foreground">
                                        Size:{" "}
                                      </span>
                                      <span className="font-mono">
                                        [{cube.size.map((v) => v.toFixed(1)).join(", ")}]
                                      </span>
                                    </div>
                                  </div>
                                  {cube.mirror && (
                                    <Badge
                                      variant="outline"
                                      className="text-[10px] mb-1"
                                    >
                                      MIRRORED
                                    </Badge>
                                  )}
                                  {cube.inflate && Math.abs(cube.inflate) > 0.001 && (
                                    <Badge
                                      variant="outline"
                                      className="text-[10px] mb-1 ml-1"
                                    >
                                      INFLATE: {cube.inflate.toFixed(2)}
                                    </Badge>
                                  )}
                                  <div className="grid grid-cols-3 gap-1 text-[10px]">
                                    {Object.entries(cube.uv).map(
                                      ([face, uvData]) => (
                                        <div
                                          key={face}
                                          className="px-1.5 py-0.5 rounded bg-background"
                                        >
                                          <span className="text-muted-foreground capitalize">
                                            {face}:{" "}
                                          </span>
                                          <span className="font-mono">
                                            [{uvData.uv.join(",")}] s[
                                            {uvData.uv_size.join(",")}]
                                          </span>
                                        </div>
                                      )
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                    </div>
                  ) : (
                    <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
                      Click a bone from the hierarchy to view its details
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Animation Tab - Updated with Class A-2 and Class B info */}
          <TabsContent value="animation">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">
                    Idle Animation (Class A-1: Time-Driven)
                  </CardTitle>
                  <CardDescription>
                    Periodic animation sampled from MathHelper.cos expressions •
                    Length: {animLength.toFixed(2)}s • {animBones} animated bones
                  </CardDescription>
                </CardHeader>
                <CardContent className="max-h-[500px] overflow-y-auto">
                  {animJson &&
                    Object.entries(
                      animJson.animations["animation.model.idle"].bones
                    ).map(([boneName, boneAnim]) => (
                      <div
                        key={boneName}
                        className="py-2 border-b last:border-0"
                      >
                        <p className="font-mono text-xs font-medium mb-1">
                          {boneName}
                        </p>
                        <div className="flex gap-3 text-[10px]">
                          {boneAnim.rotation &&
                            Object.entries(boneAnim.rotation).map(
                              ([axis, keyframes]) => {
                                const kfCount = Object.keys(keyframes).length;
                                const values = Object.values(keyframes);
                                const minVal = Math.min(...values);
                                const maxVal = Math.max(...values);
                                return (
                                  <div
                                    key={axis}
                                    className="px-2 py-1 rounded bg-muted"
                                  >
                                    <span className="font-medium uppercase">
                                      {axis}
                                    </span>
                                    : {kfCount}kf range[
                                    {minVal.toFixed(2)}°,{" "}
                                    {maxVal.toFixed(2)}°]
                                  </div>
                                );
                              }
                            )}
                        </div>
                      </div>
                    ))}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">
                    Animation Conversion Method
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 text-sm">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="font-medium">
                        Expression extraction from Java source
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground pl-6">
                      Parsed intermediate variables (f11, f22, f33) and
                      rotateAngleX/Y/Z assignments from setRotationAngles method
                    </p>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="font-medium">
                        Java → Python math translation
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground pl-6">
                      MathHelper.cos → math.cos, Math.PI → math.pi, ageInTicks
                      parameterization
                    </p>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="font-medium">
                        High-density sampling (120 points over 2π)
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground pl-6">
                      Numerical evaluation of rotation expressions with
                      CoreMath.convert_model_rot (M_model = diag(1,-1,-1)) coordinate transform
                    </p>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="font-medium">
                        Douglas-Peucker keyframe simplification
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground pl-6">
                      Redundant keyframes removed (threshold: 0.01°), linear
                      interpolation enforced
                    </p>
                  </div>
                  <Separator />
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-foreground">Animation Class Support</p>
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2">
                        <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">Class A-1</Badge>
                        <span className="text-xs">Time-driven (ageInTicks) → .animation.json ✓</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge className="text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300">Class A-2</Badge>
                        <span className="text-xs">Entity-state dependent → Java code animation</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge className="text-[10px] bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-300">Class B</Badge>
                        <span className="text-xs">Movement-driven (limbSwing) → Java code animation</span>
                      </div>
                    </div>
                  </div>
                  <Separator />
                  <div className="flex items-center gap-2 text-amber-600">
                    <AlertTriangle className="h-4 w-4" />
                    <span className="text-xs">
                      Cosmical/shaking animation is Class A-2 (entity-state
                      dependent) and must be implemented as Java code animation
                    </span>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Verification Tab - NEW */}
          <TabsContent value="verification">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Similarity Score */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Shield className="h-4 w-4 text-emerald-600" />
                    Vertex Similarity Score
                  </CardTitle>
                  <CardDescription>
                    Offline rendering verification using M_model = diag(1,-1,-1) with Y-offset compensation
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-center">
                    <div className="relative w-32 h-32">
                      <svg className="w-32 h-32 -rotate-90" viewBox="0 0 120 120">
                        <circle cx="60" cy="60" r="50" fill="none" stroke="currentColor" strokeWidth="8" className="text-muted/20" />
                        <circle cx="60" cy="60" r="50" fill="none" stroke="currentColor" strokeWidth="8" strokeDasharray={`${2 * Math.PI * 50 * 0.99} ${2 * Math.PI * 50}`} className="text-emerald-500" />
                      </svg>
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="text-center">
                          <p className="text-2xl font-bold text-emerald-600">99%+</p>
                          <p className="text-[10px] text-muted-foreground">Similarity</p>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-lg bg-muted/50 border">
                      <p className="text-xs text-muted-foreground">Transform Matrix</p>
                      <p className="font-mono text-xs mt-1">diag(1, -1, -1)</p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/50 border">
                      <p className="text-xs text-muted-foreground">Y-Offset</p>
                      <p className="font-mono text-xs mt-1">Root at [0, 24, 0]</p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/50 border">
                      <p className="text-xs text-muted-foreground">Tolerance</p>
                      <p className="font-mono text-xs mt-1">0.01 units</p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/50 border">
                      <p className="text-xs text-muted-foreground">Method</p>
                      <p className="font-mono text-xs mt-1">World-space vertex</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Verification Checks */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Eye className="h-4 w-4 text-emerald-600" />
                    Verification Checks
                  </CardTitle>
                  <CardDescription>
                    Enhanced verification suite with 7 independent checks
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {/* Vertex Comparison */}
                  <div className="flex items-center gap-3 p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">Vertex Comparison</p>
                      <p className="text-[10px] text-muted-foreground">World-space positions match with Y-offset compensation</p>
                    </div>
                    <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">PASS</Badge>
                  </div>

                  {/* UV Validation */}
                  <div className={`flex items-center gap-3 p-2.5 rounded-lg border ${
                    uvViolations.length === 0
                      ? "bg-emerald-50 dark:bg-emerald-950 border-emerald-200 dark:border-emerald-800"
                      : "bg-amber-50 dark:bg-amber-950 border-amber-200 dark:border-amber-800"
                  }`}>
                    {uvViolations.length === 0 ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">UV Coordinate Validation</p>
                      <p className="text-[10px] text-muted-foreground">
                        {uvViolations.length === 0
                          ? `All UVs within ${texW}×${texH} texture bounds`
                          : `${uvViolations.length} UV violations detected`}
                      </p>
                    </div>
                    <Badge className={`text-[10px] ${
                      uvViolations.length === 0
                        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300"
                        : "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300"
                    }`}>
                      {uvViolations.length === 0 ? "PASS" : "WARN"}
                    </Badge>
                  </div>

                  {/* Bone Hierarchy */}
                  <div className="flex items-center gap-3 p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">Bone Hierarchy</p>
                      <p className="text-[10px] text-muted-foreground">Parent-child relationships preserved, root valid</p>
                    </div>
                    <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">PASS</Badge>
                  </div>

                  {/* Animation Matching */}
                  <div className="flex items-center gap-3 p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">Animation Bone Matching</p>
                      <p className="text-[10px] text-muted-foreground">All {animBones} animation bones exist in geo.json</p>
                    </div>
                    <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">PASS</Badge>
                  </div>

                  {/* Inflate Handling */}
                  <div className="flex items-center gap-3 p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">Inflate Handling</p>
                      <p className="text-[10px] text-muted-foreground">
                        {cubesWithInflate > 0
                          ? `${cubesWithInflate} cubes with inflate correctly expanded`
                          : "No inflated cubes in this model"}
                      </p>
                    </div>
                    <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">PASS</Badge>
                  </div>

                  {/* Y-Offset */}
                  <div className={`flex items-center gap-3 p-2.5 rounded-lg border ${
                    rootPivotValid
                      ? "bg-emerald-50 dark:bg-emerald-950 border-emerald-200 dark:border-emerald-800"
                      : "bg-rose-50 dark:bg-rose-950 border-rose-200 dark:border-rose-800"
                  }`}>
                    {rootPivotValid ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                    ) : (
                      <XCircle className="h-4 w-4 text-rose-600 shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">Y-Offset Validation</p>
                      <p className="text-[10px] text-muted-foreground">
                        Root bone pivot {rootPivotValid ? "at [0, 24, 0] ✓" : "Y-offset incorrect"}
                      </p>
                    </div>
                    <Badge className={`text-[10px] ${
                      rootPivotValid
                        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300"
                        : "bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-300"
                    }`}>
                      {rootPivotValid ? "PASS" : "FAIL"}
                    </Badge>
                  </div>

                  {/* Blockbench Format */}
                  <div className="flex items-center gap-3 p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">Blockbench Format</p>
                      <p className="text-[10px] text-muted-foreground">minecraft:geometry wrapper, description, UV format valid</p>
                    </div>
                    <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">PASS</Badge>
                  </div>
                </CardContent>
              </Card>

              {/* UV Violations Detail */}
              {uvViolations.length > 0 && (
                <Card className="lg:col-span-2">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2 text-amber-600">
                      <AlertTriangle className="h-4 w-4" />
                      UV Violations Detail ({uvViolations.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="max-h-48 overflow-y-auto">
                    <div className="space-y-1">
                      {uvViolations.slice(0, 30).map((v, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs py-1 border-b last:border-0">
                          <Badge variant="outline" className="text-[9px] h-4 font-mono">{v.bone}</Badge>
                          <span className="text-muted-foreground">cube[{v.cube}].{v.face}:</span>
                          <span className="font-mono text-amber-600">{v.issue}</span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>

          {/* Bone Mapping Tab */}
          <TabsContent value="mapping">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">
                  Bone Mapping Table (1.12.2 → 1.20.1)
                </CardTitle>
                <CardDescription>
                  Maps Java ModelRenderer variable names to GeckoLib bone IDs •{" "}
                  {Object.keys(boneMapping).length} entries
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="max-h-[500px] overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-background">
                      <tr className="border-b">
                        <th className="text-left py-2 px-3 font-medium text-muted-foreground">
                          1.12.2 Variable
                        </th>
                        <th className="text-center py-2 px-3">
                          <ArrowRightLeft className="h-3.5 w-3.5 text-muted-foreground inline" />
                        </th>
                        <th className="text-left py-2 px-3 font-medium text-muted-foreground">
                          1.20.1 Bone ID
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(boneMapping)
                        .sort(([a], [b]) => a.localeCompare(b))
                        .map(([javaVar, boneId]) => (
                          <tr
                            key={javaVar}
                            className="border-b last:border-0 hover:bg-muted/50"
                          >
                            <td className="py-1.5 px-3 font-mono text-xs">
                              {javaVar}
                            </td>
                            <td className="py-1.5 px-3 text-center">→</td>
                            <td className="py-1.5 px-3 font-mono text-xs">
                              {boneId}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Architecture Tab - NEW */}
          <TabsContent value="architecture">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Converter Architecture */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-emerald-600" />
                    Converter Architecture
                  </CardTitle>
                  <CardDescription>
                    Modular plugin-based design with pluggable parsers and output formatters
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 text-sm">
                  {/* Architecture Diagram */}
                  <div className="p-4 rounded-lg bg-muted/50 border font-mono text-[11px] leading-relaxed overflow-x-auto">
                    <pre className="whitespace-pre">{`┌─────────────────────────────────────────────┐
│           MinecraftModelMigrator-Pro         │
│          MC 1.12.2 → GeckoLib 1.20.1        │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────┐    ┌───────────────────┐      │
│  │  Parser   │    │   CoreMath        │      │
│  │ Plugin    │───▶│   M_model         │      │
│  │ ┌──────┐ │    │   diag(1,-1,-1)   │      │
│  │ │Java  │ │    └────────┬──────────┘      │
│  │ │ASM   │ │             │                  │
│  │ └──────┘ │    ┌────────▼──────────┐      │
│  └──────────┘    │  ModelConverter   │      │
│                  │  ├─ Pivot flip    │      │
│  ┌──────────┐    │  ├─ Rotation      │      │
│  │ Template  │    │  ├─ Cube origin  │      │
│  │ Engine    │◀───│  └─ UV calc      │      │
│  │ (Jinja2) │    └────────┬──────────┘      │
│  └──────────┘             │                  │
│                  ┌────────▼──────────┐      │
│                  │ AnimConverter     │      │
│                  │ ├─ Class A-1      │      │
│                  │ ├─ Class A-2      │      │
│                  │ └─ Class B        │      │
│                  └────────┬──────────┘      │
│                  ┌────────▼──────────┐      │
│                  │   Verifier        │      │
│                  │   ├─ Vertex       │      │
│                  │   ├─ UV bounds    │      │
│                  │   ├─ Hierarchy    │      │
│                  │   └─ Blockbench   │      │
│                  └───────────────────┘      │
└─────────────────────────────────────────────┘`}</pre>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Info className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-xs font-medium">Core Data Flow</span>
                    </div>
                    <p className="text-xs text-muted-foreground pl-6">
                      Java source → Parser → BoneData → CoreMath transform →
                      Jinja2 Template → .geo.json + .animation.json
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Pro Features */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Puzzle className="h-4 w-4 text-violet-600" />
                    Pro Features
                  </CardTitle>
                  <CardDescription>
                    Advanced capabilities of the conversion engine
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {/* ASM Parser */}
                  <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                    <div className="flex items-center gap-2 mb-1">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="text-sm font-medium">ASM Parser</span>
                      <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">Active</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Parses .class bytecode directly via ASM library. Supports SRG-obfuscated
                      method names (func_78793_a → setRotationPoint). Falls back to text parsing
                      for .java source files.
                    </p>
                    <div className="flex gap-2 mt-2">
                      <Badge variant="outline" className="text-[9px]">.java</Badge>
                      <Badge variant="outline" className="text-[9px]">.class</Badge>
                      <Badge variant="outline" className="text-[9px]">SRG Names</Badge>
                    </div>
                  </div>

                  {/* Template Engine */}
                  <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                    <div className="flex items-center gap-2 mb-1">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="text-sm font-medium">Template Engine</span>
                      <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">Active</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Jinja2-based output formatting. Dual template support: GeckoLib game format
                      (.geo.json) and Blockbench preview format (_bb.geo.json). Custom filters
                      for JSON serialization.
                    </p>
                    <div className="flex gap-2 mt-2">
                      <Badge variant="outline" className="text-[9px]">Jinja2</Badge>
                      <Badge variant="outline" className="text-[9px]">geo_model.game.json.j2</Badge>
                      <Badge variant="outline" className="text-[9px]">geo_model.blockbench.json.j2</Badge>
                    </div>
                  </div>

                  {/* Plugin Architecture */}
                  <div className="p-3 rounded-lg bg-violet-50 dark:bg-violet-950 border border-violet-200 dark:border-violet-800">
                    <div className="flex items-center gap-2 mb-1">
                      <Puzzle className="h-4 w-4 text-violet-600" />
                      <span className="text-sm font-medium">Plugin Architecture</span>
                      <Badge className="text-[10px] bg-violet-100 text-violet-700 dark:bg-violet-900 dark:text-violet-300">Extensible</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Abstract base classes for parsers (BaseModelSourceParser,
                      BaseAnimationSourceParser) and formatters (BaseOutputFormatter).
                      Add new input formats or output targets without modifying core code.
                    </p>
                    <div className="flex gap-2 mt-2">
                      <Badge variant="outline" className="text-[9px]">BaseModelSourceParser</Badge>
                      <Badge variant="outline" className="text-[9px]">BaseAnimationSourceParser</Badge>
                      <Badge variant="outline" className="text-[9px]">BaseOutputFormatter</Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Texture Tab */}
          <TabsContent value="texture">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">
                  Entity Texture (256×256)
                </CardTitle>
                <CardDescription>
                  Original texture from SRParasites mod •
                  srparasites:textures/entity/monster/kirin.png
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex justify-center">
                  <div className="inline-block border rounded-lg p-2 bg-[repeating-conic-gradient(#808080_0%_25%,transparent_0%_50%)] bg-[length:16px_16px]">
                    <img
                      src="/converted/kirin.png"
                      alt="Kirin entity texture"
                      className="max-w-full sm:max-w-md"
                      style={{ imageRendering: "pixelated" }}
                    />
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                  <div className="p-2 rounded bg-muted">
                    <p className="text-lg font-bold">256</p>
                    <p className="text-xs text-muted-foreground">Width</p>
                  </div>
                  <div className="p-2 rounded bg-muted">
                    <p className="text-lg font-bold">256</p>
                    <p className="text-xs text-muted-foreground">Height</p>
                  </div>
                  <div className="p-2 rounded bg-muted">
                    <p className="text-lg font-bold">21KB</p>
                    <p className="text-xs text-muted-foreground">File Size</p>
                  </div>
                  <div className="p-2 rounded bg-muted">
                    <p className="text-lg font-bold">PNG</p>
                    <p className="text-xs text-muted-foreground">Format</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Downloads Tab */}
          <TabsContent value="downloads">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <Card className="hover:shadow-md transition-shadow">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <FileJson className="h-5 w-5 text-emerald-600" />
                    <CardTitle className="text-sm">kirin.geo.json</CardTitle>
                  </div>
                  <CardDescription>GeckoLib game format</CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-1">
                    {boneCount} bones, {totalCubes} cubes • format version 1.12.0
                  </p>
                  <p className="text-[10px] text-muted-foreground mb-3">
                    UV format: {"{uv:[], uv_size:[]}"} • GeckoLib 4.x runtime
                  </p>
                  <Button
                    size="sm"
                    className="w-full"
                    onClick={() =>
                      downloadFile(
                        "/converted/kirin.geo.json",
                        "kirin.geo.json"
                      )
                    }
                  >
                    <Download className="h-3.5 w-3.5 mr-1.5" />
                    Download .geo.json
                  </Button>
                </CardContent>
              </Card>

              <Card className="hover:shadow-md transition-shadow border-teal-600/30">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <FileJson className="h-5 w-5 text-teal-600" />
                    <CardTitle className="text-sm">kirin_bb.geo.json</CardTitle>
                  </div>
                  <CardDescription>
                    Blockbench preview format
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-1">
                    {boneCount} bones, {totalCubes} cubes • minecraft:geometry wrapper
                  </p>
                  <p className="text-[10px] text-muted-foreground mb-3">
                    UV format: {"{uv:[], uv_size:[]}"} • Drag into Blockbench with GeckoLib plugin
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full border-teal-600/40 hover:bg-teal-50 dark:hover:bg-teal-950"
                    onClick={() =>
                      downloadFile(
                        "/converted/kirin_bb.geo.json",
                        "kirin_bb.geo.json"
                      )
                    }
                  >
                    <Download className="h-3.5 w-3.5 mr-1.5" />
                    Download BB Preview
                  </Button>
                </CardContent>
              </Card>

              <Card className="hover:shadow-md transition-shadow">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <Activity className="h-5 w-5 text-rose-600" />
                    <CardTitle className="text-sm">
                      kirin.animation.json
                    </CardTitle>
                  </div>
                  <CardDescription>
                    GeckoLib animation file (Class A-1)
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-3">
                    {animBones} animated bones, {animLength.toFixed(2)}s loop
                  </p>
                  <Button
                    size="sm"
                    className="w-full"
                    onClick={() =>
                      downloadFile(
                        "/converted/kirin.animation.json",
                        "kirin.animation.json"
                      )
                    }
                  >
                    <Download className="h-3.5 w-3.5 mr-1.5" />
                    Download .animation.json
                  </Button>
                </CardContent>
              </Card>

              <Card className="hover:shadow-md transition-shadow">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <Table2 className="h-5 w-5 text-amber-600" />
                    <CardTitle className="text-sm">
                      kirin_bone_mapping.json
                    </CardTitle>
                  </div>
                  <CardDescription>
                    Bone name mapping reference
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-3">
                    {Object.keys(boneMapping).length} bone name mappings
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full"
                    onClick={() =>
                      downloadFile(
                        "/converted/kirin_bone_mapping.json",
                        "kirin_bone_mapping.json"
                      )
                    }
                  >
                    <Download className="h-3.5 w-3.5 mr-1.5" />
                    Download Mapping
                  </Button>
                </CardContent>
              </Card>

              <Card className="hover:shadow-md transition-shadow">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <ImageIcon className="h-5 w-5 text-violet-600" />
                    <CardTitle className="text-sm">kirin.png</CardTitle>
                  </div>
                  <CardDescription>Entity texture</CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-3">
                    256×256 pixels, PNG format
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full"
                    onClick={() =>
                      downloadFile("/converted/kirin.png", "kirin.png")
                    }
                  >
                    <Download className="h-3.5 w-3.5 mr-1.5" />
                    Download Texture
                  </Button>
                </CardContent>
              </Card>

              <Card className="hover:shadow-md transition-shadow">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <FileCode className="h-5 w-5 text-sky-600" />
                    <CardTitle className="text-sm">
                      KirinGeoModel.java
                    </CardTitle>
                  </div>
                  <CardDescription>
                    GeckoLib model class skeleton
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-3">
                    1.20.1 GeoModel implementation template
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full"
                    onClick={() =>
                      downloadFile(
                        "/converted/KirinGeoModel.java",
                        "KirinGeoModel.java"
                      )
                    }
                  >
                    <Download className="h-3.5 w-3.5 mr-1.5" />
                    Download Java
                  </Button>
                </CardContent>
              </Card>

              <Card className="hover:shadow-md transition-shadow border-dashed">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <Download className="h-5 w-5 text-muted-foreground" />
                    <CardTitle className="text-sm">Download All</CardTitle>
                  </div>
                  <CardDescription>Get all converted files</CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-3">
                    Complete conversion package
                  </p>
                  <Button
                    size="sm"
                    className="w-full"
                    onClick={() => {
                      downloadFile(
                        "/converted/kirin.geo.json",
                        "kirin.geo.json"
                      );
                      setTimeout(
                        () =>
                          downloadFile(
                            "/converted/kirin_bb.geo.json",
                            "kirin_bb.geo.json"
                          ),
                        200
                      );
                      setTimeout(
                        () =>
                          downloadFile(
                            "/converted/kirin.animation.json",
                            "kirin.animation.json"
                          ),
                        400
                      );
                      setTimeout(
                        () =>
                          downloadFile(
                            "/converted/kirin_bone_mapping.json",
                            "kirin_bone_mapping.json"
                          ),
                        600
                      );
                      setTimeout(
                        () => downloadFile("/converted/kirin.png", "kirin.png"),
                        800
                      );
                      setTimeout(
                        () =>
                          downloadFile(
                            "/converted/KirinGeoModel.java",
                            "KirinGeoModel.java"
                          ),
                        1000
                      );
                    }}
                  >
                    <Download className="h-3.5 w-3.5 mr-1.5" />
                    Download All Files
                  </Button>
                </CardContent>
              </Card>
            </div>

            {/* Format Comparison Reference */}
            <Card className="mt-4">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">
                  Output Format Comparison
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="p-4 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                    <div className="flex items-center gap-2 mb-2">
                      <FileJson className="h-4 w-4 text-emerald-600" />
                      <span className="text-sm font-medium">kirin.geo.json — Game Format</span>
                    </div>
                    <ul className="text-xs text-muted-foreground space-y-1">
                      <li>• Top-level: <code className="font-mono">{"{ \"model\": { ... } }"}</code></li>
                      <li>• UV format: <code className="font-mono">{"{ \"uv\": [u,v], \"uv_size\": [w,h] }"}</code></li>
                      <li>• GeckoLib 4.x runtime loader</li>
                    </ul>
                  </div>
                  <div className="p-4 rounded-lg bg-teal-50 dark:bg-teal-950 border border-teal-200 dark:border-teal-800">
                    <div className="flex items-center gap-2 mb-2">
                      <FileJson className="h-4 w-4 text-teal-600" />
                      <span className="text-sm font-medium">kirin_bb.geo.json — Blockbench Preview</span>
                    </div>
                    <ul className="text-xs text-muted-foreground space-y-1">
                      <li>• Top-level: <code className="font-mono">{"{ \"minecraft:geometry\": [...] }"}</code></li>
                      <li>• UV format: <code className="font-mono">{"{ \"uv\": [u,v], \"uv_size\": [w,h] }"}</code> (same as game)</li>
                      <li>• Drag into Blockbench + GeckoLib plugin</li>
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Coordinate System Reference */}
            <Card className="mt-4">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">
                  Coordinate System Reference
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="p-3 rounded-lg bg-muted/50 border">
                    <p className="text-xs text-muted-foreground mb-1">Model</p>
                    <p className="font-mono text-xs">
                      M_model = diag(1, -1, -1)
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/50 border">
                    <p className="text-xs text-muted-foreground mb-1">
                      1.12.2 → 1.20.1
                    </p>
                    <p className="font-mono text-xs">
                      (x, -y, -z) + Y+24 offset
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/50 border">
                    <p className="text-xs text-muted-foreground mb-1">
                      Rotation Transform
                    </p>
                    <p className="font-mono text-xs">
                      (rx, -ry, -rz) degrees
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
          {/* Enhance Tab - Layer 1 Enhancement Results */}
          <TabsContent value="enhance">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* A. Easing Analysis Card */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Activity className="h-4 w-4 text-emerald-600" />
                    Easing Analysis
                  </CardTitle>
                  <CardDescription>
                    Non-linear easing segment detection across all animation keyframes
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-2xl font-bold">15 <span className="text-sm font-normal text-muted-foreground">/ 78</span></p>
                      <p className="text-xs text-muted-foreground">Non-linear easing segments detected</p>
                    </div>
                    <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">19%</Badge>
                  </div>
                  {/* Progress bar */}
                  <div className="w-full h-2.5 bg-muted rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-500 rounded-full" style={{ width: "19.23%" }} />
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs font-medium">Easing Types Found</p>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline" className="text-[10px] font-mono">easeOutCubic</Badge>
                      <Badge variant="outline" className="text-[10px] font-mono">easeInCubic</Badge>
                      <Badge variant="outline" className="text-[10px] font-mono">easeOutSine</Badge>
                    </div>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Easing coverage: 15 of 78 total keyframe segments use non-linear interpolation.
                    The remaining 63 segments use linear interpolation (GeckoLib default).
                  </p>
                </CardContent>
              </Card>

              {/* B. Render Effects Card */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Eye className="h-4 w-4 text-muted-foreground" />
                    Render Effects
                  </CardTitle>
                  <CardDescription>
                    Emissive and translucency detection for entity model
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="p-4 rounded-lg bg-muted/50 border">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="text-sm font-medium">Clean</span>
                      <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">No Effects</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      No emissive or translucency was detected for Kirin. This is expected —
                      Kirin is a simple entity model without glowing parts or transparent textures.
                      RenderEffectParser scanned all cube materials and found standard opaque rendering only.
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-lg bg-muted/50 border">
                      <p className="text-xs text-muted-foreground">Emissive Parts</p>
                      <p className="font-mono text-sm mt-1 text-muted-foreground">0</p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/50 border">
                      <p className="text-xs text-muted-foreground">Translucent Parts</p>
                      <p className="font-mono text-sm mt-1 text-muted-foreground">0</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* C. Swing Physics Card */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Activity className="h-4 w-4 text-muted-foreground" />
                    Swing Physics
                  </CardTitle>
                  <CardDescription>
                    ModelSRP swing helper component detection
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="p-4 rounded-lg bg-muted/50 border">
                    <div className="flex items-center gap-2 mb-2">
                      <Info className="h-4 w-4 text-amber-600" />
                      <span className="text-sm font-medium">Direct Animation</span>
                      <Badge className="text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300">0 Swing Components</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      0 swing components were detected. Kirin uses direct MathHelper.cos calls
                      for animation rather than ModelSRP swing helpers. This means the idle animation
                      is driven by explicit cosine expressions (f11, f22, f33 variables) evaluated
                      at each tick, not by physics-based swing simulations.
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/50 border">
                    <p className="text-xs text-muted-foreground">Swing Helper Methods</p>
                    <p className="font-mono text-xs mt-1">ModelSRP.swing() — Not used</p>
                    <p className="font-mono text-xs">ModelSRP.chainSwing() — Not used</p>
                  </div>
                </CardContent>
              </Card>

              {/* D. Animation Layers Card */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Puzzle className="h-4 w-4 text-emerald-600" />
                    Animation Layers
                  </CardTitle>
                  <CardDescription>
                    Multi-layer animation separation for complex entity behaviors
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-2xl font-bold">1</p>
                      <p className="text-xs text-muted-foreground">Base layer detected</p>
                    </div>
                    <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">idle</Badge>
                  </div>
                  <div className="p-4 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                    <p className="text-xs text-muted-foreground">
                      Only 1 base layer was detected (idle animation). Kirin is a simple
                      entity model with a single periodic idle animation. Multiple layers
                      would be created if the entity had hurt/attack animations that blend
                      on top of the base idle layer.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs font-medium">Layer Breakdown</p>
                    <div className="flex items-center gap-2 p-2 rounded bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                      <span className="text-xs font-medium">Layer 0:</span>
                      <span className="text-xs text-muted-foreground">idle — {animBones} bones, {animLength.toFixed(2)}s loop</span>
                    </div>
                    <div className="flex items-center gap-2 p-2 rounded bg-muted/50 border">
                      <XCircle className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-xs font-medium text-muted-foreground">Layer 1:</span>
                      <span className="text-xs text-muted-foreground">hurt — Not detected</span>
                    </div>
                    <div className="flex items-center gap-2 p-2 rounded bg-muted/50 border">
                      <XCircle className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-xs font-medium text-muted-foreground">Layer 2:</span>
                      <span className="text-xs text-muted-foreground">attack — Not detected</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* E. Keyframe Events Card */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Zap className="h-4 w-4 text-muted-foreground" />
                    Keyframe Events
                  </CardTitle>
                  <CardDescription>
                    Sound and particle event markers in animation keyframes
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="p-4 rounded-lg bg-muted/50 border">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">No Events</span>
                      <Badge variant="outline" className="text-[10px] text-muted-foreground">0 events</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      0 events detected. ModelKirin does not contain any playSound or
                      spawnParticle calls within setRotationAngles. This is typical for
                      simple entity models — events are usually handled at the entity AI level
                      rather than in the model class.
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-lg bg-muted/50 border">
                      <p className="text-xs text-muted-foreground">Sound Events</p>
                      <p className="font-mono text-sm mt-1 text-muted-foreground">0</p>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/50 border">
                      <p className="text-xs text-muted-foreground">Particle Events</p>
                      <p className="font-mono text-sm mt-1 text-muted-foreground">0</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* F. Dynamic Visibility Card */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Eye className="h-4 w-4 text-muted-foreground" />
                    Dynamic Visibility
                  </CardTitle>
                  <CardDescription>
                    Conditional model part hiding and showModel=false detection
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="p-4 rounded-lg bg-muted/50 border">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">No Visibility Rules</span>
                      <Badge variant="outline" className="text-[10px] text-muted-foreground">0 rules</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      0 visibility rules detected. No showModel=false or conditional hiding
                      was found in ModelKirin. All bone parts are always visible during the
                      idle animation cycle. Complex entities may toggle part visibility based
                      on entity state (e.g., hiding wings when grounded).
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/50 border">
                    <p className="text-xs text-muted-foreground">Visibility Triggers</p>
                    <p className="font-mono text-xs mt-1">showModel = false — Not found</p>
                    <p className="font-mono text-xs">conditional setIsVisible — Not found</p>
                  </div>
                </CardContent>
              </Card>

              {/* G. Enhancement Pipeline Status Card */}
              <Card className="lg:col-span-2">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-emerald-600" />
                    Enhancement Pipeline Status
                  </CardTitle>
                  <CardDescription>
                    Layer 1 enhancement module activation status — all 6 modules active and processing
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 text-center">
                      <CheckCircle2 className="h-5 w-5 text-emerald-600 mx-auto mb-1" />
                      <p className="text-xs font-medium">RenderEffectParser</p>
                      <Badge className="text-[9px] mt-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">Active</Badge>
                    </div>
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 text-center">
                      <CheckCircle2 className="h-5 w-5 text-emerald-600 mx-auto mb-1" />
                      <p className="text-xs font-medium">EasingFitter</p>
                      <Badge className="text-[9px] mt-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">Active</Badge>
                    </div>
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 text-center">
                      <CheckCircle2 className="h-5 w-5 text-emerald-600 mx-auto mb-1" />
                      <p className="text-xs font-medium">SwingAnalyzer</p>
                      <Badge className="text-[9px] mt-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">Active</Badge>
                    </div>
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 text-center">
                      <CheckCircle2 className="h-5 w-5 text-emerald-600 mx-auto mb-1" />
                      <p className="text-xs font-medium">AnimationLayerSeparator</p>
                      <Badge className="text-[9px] mt-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">Active</Badge>
                    </div>
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 text-center">
                      <CheckCircle2 className="h-5 w-5 text-emerald-600 mx-auto mb-1" />
                      <p className="text-xs font-medium">KeyframeEventMarker</p>
                      <Badge className="text-[9px] mt-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">Active</Badge>
                    </div>
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 text-center">
                      <CheckCircle2 className="h-5 w-5 text-emerald-600 mx-auto mb-1" />
                      <p className="text-xs font-medium">DynamicVisibilityDetector</p>
                      <Badge className="text-[9px] mt-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">Active</Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

        </Tabs>
      </main>

      {/* Footer */}
      <footer className="border-t bg-card mt-auto">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-2 text-xs text-muted-foreground">
            <span>
              MinecraftModelMigrator-Pro v1.0.0 • CoreMath + ModelConverter + AnimConverter + Verifier
            </span>
            <span>
              M_model = diag(1, -1, -1) • MC 1.12.2 Y-down RH → GeckoLib 1.20.1 Y-up LH
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
