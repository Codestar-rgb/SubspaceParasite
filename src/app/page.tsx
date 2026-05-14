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

  // Build bone hierarchy
  const boneMap = new Map<string, BoneData>();
  const childrenMap = new Map<string, string[]>();
  geoJson?.model.bones.forEach((bone) => {
    boneMap.set(bone.name, bone);
    const parent = bone.parent ?? "root";
    if (!childrenMap.has(parent)) childrenMap.set(parent, []);
    childrenMap.get(parent)!.push(bone.name);
  });

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
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800">
                <CheckCircle2 className="h-4 w-4 text-amber-600" />
                <span className="text-sm font-medium">Verifier</span>
                <Badge variant="secondary" className="text-[10px]">
                  Vertex
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Main Tabs */}
        <Tabs defaultValue="model" className="space-y-4">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="model" className="gap-1.5">
              <Box className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Model</span>
            </TabsTrigger>
            <TabsTrigger value="animation" className="gap-1.5">
              <Activity className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Animation</span>
            </TabsTrigger>
            <TabsTrigger value="mapping" className="gap-1.5">
              <Table2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Mapping</span>
            </TabsTrigger>
            <TabsTrigger value="texture" className="gap-1.5">
              <ImageIcon className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Texture</span>
            </TabsTrigger>
            <TabsTrigger value="downloads" className="gap-1.5">
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Files</span>
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

          {/* Animation Tab */}
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
                  <CardDescription>GeckoLib 游戏格式</CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-1">
                    {boneCount} bones, {totalCubes} cubes • format version 1.12.0
                  </p>
                  <p className="text-[10px] text-muted-foreground mb-3">
                    UV 格式: {"{uv:[], uv_size:[]}"} • GeckoLib 4.x 运行时加载
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
                    Blockbench 预览格式
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground mb-1">
                    {boneCount} bones, {totalCubes} cubes • minecraft:geometry 包装
                  </p>
                  <p className="text-[10px] text-muted-foreground mb-3">
                    UV 格式: {"{uv:[], uv_size:[]}"} • 拖入 Blockbench + GeckoLib 插件即可预览
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
                  输出格式对比
                </CardTitle>
                <CardDescription>
                  两种 .geo.json 格式的差异及适用场景
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="p-4 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                    <div className="flex items-center gap-2 mb-2">
                      <FileJson className="h-4 w-4 text-emerald-600" />
                      <span className="text-sm font-medium">kirin.geo.json — 游戏格式</span>
                    </div>
                    <ul className="text-xs text-muted-foreground space-y-1">
                      <li>• 顶层包装: <code className="font-mono">{"{ \"model\": { ... } }"}</code></li>
                      <li>• UV 格式: <code className="font-mono">{"{ \"uv\": [u,v], \"uv_size\": [w,h] }"}</code></li>
                      <li>• 适用: GeckoLib 4.x 运行时加载</li>
                      <li>• 直接放入 mod 资源包即可使用</li>
                    </ul>
                  </div>
                  <div className="p-4 rounded-lg bg-teal-50 dark:bg-teal-950 border border-teal-200 dark:border-teal-800">
                    <div className="flex items-center gap-2 mb-2">
                      <FileJson className="h-4 w-4 text-teal-600" />
                      <span className="text-sm font-medium">kirin_bb.geo.json — Blockbench 预览格式</span>
                    </div>
                    <ul className="text-xs text-muted-foreground space-y-1">
                      <li>• 顶层包装: <code className="font-mono">{"{ \"minecraft:geometry\": [...] }"}</code></li>
                      <li>• UV 格式: <code className="font-mono">{"{ \"uv\": [u,v], \"uv_size\": [w,h] }"}</code> (与游戏格式相同)</li>
                      <li>• 适用: Blockbench + GeckoLib 插件预览/编辑</li>
                      <li>• 拖入 Blockbench 后分配 kirin.png 贴图验证</li>
                    </ul>
                  </div>
                </div>
                <p className="text-[10px] text-muted-foreground mt-3">
                  ⚠ 两种格式的数学变换（坐标、旋转、尺寸）和 UV 格式完全一致，仅 JSON 顶层包装结构不同。
                  不要将 Blockbench 格式文件放入 mod 资源包，GeckoLib 无法加载 minecraft:geometry 包装。
                </p>
              </CardContent>
            </Card>

            {/* Resource Locations Reference */}
            <Card className="mt-4">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">
                  GeckoLib Resource Locations
                </CardTitle>
                <CardDescription>
                  Use these paths in your 1.20.1 mod resource pack
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="p-3 rounded-lg bg-muted/50 border">
                    <p className="text-xs text-muted-foreground mb-1">Model</p>
                    <p className="font-mono text-xs">
                      srparasites:geo/entity/kirin.geo.json
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/50 border">
                    <p className="text-xs text-muted-foreground mb-1">
                      Texture
                    </p>
                    <p className="font-mono text-xs">
                      srparasites:textures/entity/monster/kirin.png
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/50 border">
                    <p className="text-xs text-muted-foreground mb-1">
                      Animation
                    </p>
                    <p className="font-mono text-xs">
                      srparasites:animations/entity/kirin.animation.json
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>

      {/* Footer */}
      <footer className="border-t bg-card mt-auto">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-2 text-xs text-muted-foreground">
            <p>
              MC 1.12.2 → GeckoLib 1.20.1 Conversion Engine • CoreMath +
              ModelConverter + AnimationConverter
            </p>
            <p>
              Source: SRParasites-1.10.4.jar • Entity: Kirin •{" "}
              {new Date().toLocaleDateString()}
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
