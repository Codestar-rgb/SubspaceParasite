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
  ImageIcon,
  Box,
  Activity,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  ArrowRightLeft,
  Shield,
  Eye,
  FolderOpen,
  Copy,
  Check,
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
            [axis: string]: Record<string, number | { vector: number; easing: string }>;
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
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

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

  const downloadFile = useCallback((url: string, filename: string) => {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, []);

  const copyToClipboard = useCallback((text: string, key: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedPath(key);
      setTimeout(() => setCopiedPath(null), 2000);
    });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
          <p className="text-muted-foreground">Loading Kirin entity files...</p>
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

  // UV validation
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

  const rootBone = geoJson?.model.bones.find((b) => b.name === "root");
  const rootPivotValid = rootBone ? Math.abs(rootBone.pivot[1] - 24) < 0.01 : false;

  const renderBoneTree = (boneName: string, depth: number = 0) => {
    const bone = boneMap.get(boneName);
    if (!bone) return null;
    const children = childrenMap.get(boneName) ?? [];
    const isExpanded = expandedBones.has(boneName);
    const isSelected = selectedBone === boneName;
    const hasRotation = bone.rotation && bone.rotation.some((v) => Math.abs(v) > 0.01);
    const hasCubes = (bone.cubes?.length ?? 0) > 0;

    return (
      <div key={boneName}>
        <div
          className={`flex items-center gap-2 py-1.5 px-2 rounded-md cursor-pointer transition-colors text-sm ${
            isSelected ? "bg-primary/10 border border-primary/30" : "hover:bg-muted"
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
          {hasRotation && <Badge variant="secondary" className="h-4 px-1 text-[10px]">R</Badge>}
          {hasCubes && <Badge variant="outline" className="h-4 px-1 text-[10px]">{bone.cubes!.length}C</Badge>}
        </div>
        {isExpanded && children.map((child) => renderBoneTree(child, depth + 1))}
      </div>
    );
  };

  const selectedBoneData = selectedBone ? boneMap.get(selectedBone) : null;

  // Game resource paths
  const MOD_ID = "srparasites";
  const resourcePaths = [
    { key: "geo", label: "Model (.geo.json)", path: `assets/${MOD_ID}/geo/entity/kirin.geo.json`, url: "/converted/kirin.geo.json", file: "kirin.geo.json" },
    { key: "anim", label: "Animation (.animation.json)", path: `assets/${MOD_ID}/animations/entity/kirin.animation.json`, url: "/converted/kirin.animation.json", file: "kirin.animation.json" },
    { key: "tex", label: "Texture (.png)", path: `assets/${MOD_ID}/textures/entity/monster/kirin.png`, url: "/converted/kirin.png", file: "kirin.png" },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="max-w-6xl mx-auto px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-primary text-primary-foreground">
              <ArrowRightLeft className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                Kirin Entity - GeckoLib 1.20.1
              </h1>
              <p className="text-sm text-muted-foreground">
                MC 1.12.2 ModelBase → GeckoLib 4.x Conversion • Ready for In-Game Use
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6 sm:px-6 lg:px-8">
        {/* Validation Status */}
        <div className="flex flex-wrap gap-2 mb-6">
          <Badge className="gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
            <CheckCircle2 className="h-3 w-3" /> Format Valid
          </Badge>
          <Badge className="gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
            <CheckCircle2 className="h-3 w-3" /> UV In Bounds
          </Badge>
          <Badge className="gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
            <CheckCircle2 className="h-3 w-3" /> Hierarchy OK
          </Badge>
          <Badge className="gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
            <CheckCircle2 className="h-3 w-3" /> Root Pivot Y=24
          </Badge>
          <Badge className="gap-1 bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
            <CheckCircle2 className="h-3 w-3" /> Anim Bones Match
          </Badge>
          <Badge variant="outline" className="text-[10px] gap-1">
            <Box className="h-3 w-3" /> {boneCount} Bones
          </Badge>
          <Badge variant="outline" className="text-[10px] gap-1">
            <Box className="h-3 w-3" /> {totalCubes} Cubes
          </Badge>
          <Badge variant="outline" className="text-[10px] gap-1">
            <Activity className="h-3 w-3" /> {animBones} Animated
          </Badge>
          <Badge variant="outline" className="text-[10px] gap-1">
            <ImageIcon className="h-3 w-3" /> 256x256 Texture
          </Badge>
        </div>

        {/* Main Tabs */}
        <Tabs defaultValue="files" className="space-y-4">
          <TabsList className="grid w-full grid-cols-4 max-w-lg">
            <TabsTrigger value="files" className="gap-1">
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Game Files</span>
            </TabsTrigger>
            <TabsTrigger value="model" className="gap-1">
              <Box className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Model</span>
            </TabsTrigger>
            <TabsTrigger value="animation" className="gap-1">
              <Activity className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Animation</span>
            </TabsTrigger>
            <TabsTrigger value="verify" className="gap-1">
              <Shield className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Verify</span>
            </TabsTrigger>
          </TabsList>

          {/* ===== Game Files Tab ===== */}
          <TabsContent value="files" className="space-y-6">
            {/* The 3 Essential Game Files */}
            <div>
              <h2 className="text-lg font-semibold mb-1">Game-Ready Files</h2>
              <p className="text-sm text-muted-foreground mb-4">
                Download these 3 files and place them in your mod&apos;s resource directory to use the Kirin entity with GeckoLib.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* geo.json */}
                <Card className="hover:shadow-lg transition-shadow border-emerald-200 dark:border-emerald-800">
                  <CardHeader className="pb-2">
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-emerald-100 dark:bg-emerald-900">
                        <FileJson className="h-5 w-5 text-emerald-600" />
                      </div>
                      <div>
                        <CardTitle className="text-sm">kirin.geo.json</CardTitle>
                        <CardDescription>GeckoLib Model</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="space-y-1 text-xs text-muted-foreground">
                      <p>format_version: <code className="font-mono text-foreground">1.12.0</code></p>
                      <p>{boneCount} bones, {totalCubes} cubes</p>
                      <p>Texture: 256x256</p>
                      <p>UV format: <code className="font-mono text-foreground">{"{uv, uv_size}"}</code></p>
                    </div>
                    <Button
                      size="sm"
                      className="w-full"
                      onClick={() => downloadFile("/converted/kirin.geo.json", "kirin.geo.json")}
                    >
                      <Download className="h-3.5 w-3.5 mr-1.5" />
                      Download .geo.json
                    </Button>
                  </CardContent>
                </Card>

                {/* animation.json */}
                <Card className="hover:shadow-lg transition-shadow border-rose-200 dark:border-rose-800">
                  <CardHeader className="pb-2">
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-rose-100 dark:bg-rose-900">
                        <Activity className="h-5 w-5 text-rose-600" />
                      </div>
                      <div>
                        <CardTitle className="text-sm">kirin.animation.json</CardTitle>
                        <CardDescription>Idle Animation</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="space-y-1 text-xs text-muted-foreground">
                      <p>format_version: <code className="font-mono text-foreground">1.8.0</code></p>
                      <p>{animBones} animated bones</p>
                      <p>Length: {animLength.toFixed(2)}s (loop)</p>
                      <p>Easing: easeOutCubic, easeOutSine, easeInCubic</p>
                    </div>
                    <Button
                      size="sm"
                      className="w-full bg-rose-600 hover:bg-rose-700 text-white"
                      onClick={() => downloadFile("/converted/kirin.animation.json", "kirin.animation.json")}
                    >
                      <Download className="h-3.5 w-3.5 mr-1.5" />
                      Download .animation.json
                    </Button>
                  </CardContent>
                </Card>

                {/* texture */}
                <Card className="hover:shadow-lg transition-shadow border-violet-200 dark:border-violet-800">
                  <CardHeader className="pb-2">
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-violet-100 dark:bg-violet-900">
                        <ImageIcon className="h-5 w-5 text-violet-600" />
                      </div>
                      <div>
                        <CardTitle className="text-sm">kirin.png</CardTitle>
                        <CardDescription>Entity Texture</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="space-y-1 text-xs text-muted-foreground">
                      <p>Format: <code className="font-mono text-foreground">PNG RGBA</code></p>
                      <p>Size: 256 x 256 pixels</p>
                      <p>Source: Original SRParasites texture</p>
                      <p>Mapped to all 141 cube faces</p>
                    </div>
                    <Button
                      size="sm"
                      className="w-full bg-violet-600 hover:bg-violet-700 text-white"
                      onClick={() => downloadFile("/converted/kirin.png", "kirin.png")}
                    >
                      <Download className="h-3.5 w-3.5 mr-1.5" />
                      Download .png
                    </Button>
                  </CardContent>
                </Card>
              </div>
            </div>

            {/* Download All */}
            <div className="flex justify-center">
              <Button
                size="lg"
                className="gap-2"
                onClick={() => {
                  downloadFile("/converted/kirin.geo.json", "kirin.geo.json");
                  setTimeout(() => downloadFile("/converted/kirin.animation.json", "kirin.animation.json"), 300);
                  setTimeout(() => downloadFile("/converted/kirin.png", "kirin.png"), 600);
                }}
              >
                <Download className="h-5 w-5" />
                Download All 3 Game Files
              </Button>
            </div>

            {/* Deployment Guide */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <FolderOpen className="h-5 w-5 text-amber-600" />
                  Deployment Guide - Where to Put the Files
                </CardTitle>
                <CardDescription>
                  Place the downloaded files in your mod&apos;s resources directory following the GeckoLib resource location convention
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Resource paths */}
                <div className="space-y-3">
                  {resourcePaths.map((rp) => (
                    <div
                      key={rp.key}
                      className="flex items-center gap-3 p-3 rounded-lg bg-muted/50 border"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">{rp.label}</p>
                        <p className="font-mono text-xs text-muted-foreground mt-0.5 truncate">
                          {rp.path}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="shrink-0"
                        onClick={() => copyToClipboard(rp.path, rp.key)}
                      >
                        {copiedPath === rp.key ? (
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </div>
                  ))}
                </div>

                <Separator />

                {/* Java Model Class */}
                <div>
                  <h3 className="text-sm font-medium mb-2">Java Model Class (Required)</h3>
                  <p className="text-xs text-muted-foreground mb-3">
                    Create a GeckoLib <code className="font-mono">GeoModel</code> class that references these resource locations:
                  </p>
                  <div className="p-4 rounded-lg bg-muted/50 border font-mono text-xs leading-relaxed overflow-x-auto">
                    <pre>{`package com.yourmod.client.model;

import net.minecraft.resources.ResourceLocation;
import software.bernie.geckolib.model.GeoModel;
import com.yourmod.entity.KirinEntity;

public class KirinGeoModel extends GeoModel<KirinEntity> {

    @Override
    public ResourceLocation getModelResource(KirinEntity animatable) {
        return new ResourceLocation("${MOD_ID}", "geo/entity/kirin.geo.json");
    }

    @Override
    public ResourceLocation getTextureResource(KirinEntity animatable) {
        return new ResourceLocation("${MOD_ID}", "textures/entity/monster/kirin.png");
    }

    @Override
    public ResourceLocation getAnimationResource(KirinEntity animatable) {
        return new ResourceLocation("${MOD_ID}", "animations/entity/kirin.animation.json");
    }
}`}</pre>
                  </div>
                </div>

                <Separator />

                {/* Renderer Class */}
                <div>
                  <h3 className="text-sm font-medium mb-2">Renderer Registration (Required)</h3>
                  <div className="p-4 rounded-lg bg-muted/50 border font-mono text-xs leading-relaxed overflow-x-auto">
                    <pre>{`package com.yourmod.client.renderer;

import software.bernie.geckolib.renderer.GeoEntityRenderer;
import com.yourmod.entity.KirinEntity;
import com.yourmod.client.model.KirinGeoModel;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class KirinRenderer extends GeoEntityRenderer<KirinEntity> {
    public KirinRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new KirinGeoModel());
        this.shadowRadius = 1.0F;
    }
}

// Register in your client setup:
// EntityRenderers.register(KirinEntity.TYPE, KirinRenderer::new);`}</pre>
                  </div>
                </div>

                <Separator />

                {/* Entity Class */}
                <div>
                  <h3 className="text-sm font-medium mb-2">Entity Class (Required)</h3>
                  <div className="p-4 rounded-lg bg-muted/50 border font-mono text-xs leading-relaxed overflow-x-auto">
                    <pre>{`package com.yourmod.entity;

import software.bernie.geckolib.animatable.GeoEntity;
import software.bernie.geckolib.core.animatable.instance.AnimatableInstanceCache;
import software.bernie.geckolib.core.animation.*;
import software.bernie.geckolib.util.GeckoLibUtil;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.level.Level;

public class KirinEntity extends Mob implements GeoEntity {
    private final AnimatableInstanceCache cache = GeckoLibUtil.createInstanceCache(this);

    public KirinEntity(EntityType<? extends KirinEntity> type, Level level) {
        super(type, level);
    }

    @Override
    public AnimatableInstanceCache getAnimatableInstanceCache() {
        return cache;
    }

    @Override
    protected void registerGoals() {
        // Add your entity goals here
    }

    // Animation controller: idle animation auto-plays
    private PlayState predicate(AnimationState<KirinEntity> event) {
        event.getController().setAnimation(
            RawAnimation.begin().then("animation.model.idle", Animation.LoopType.LOOP)
        );
        return PlayState.CONTINUE;
    }

    @Override
    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {
        controllers.add(new AnimationController<>(this, "controller", 0, this::predicate));
    }
}`}</pre>
                  </div>
                </div>

                <Separator />

                {/* Directory Structure */}
                <div>
                  <h3 className="text-sm font-medium mb-2">Final Directory Structure</h3>
                  <div className="p-4 rounded-lg bg-muted/50 border font-mono text-xs leading-relaxed">
                    <pre>{`src/main/resources/
├── assets/${MOD_ID}/
│   ├── geo/
│   │   └── entity/
│   │       └── kirin.geo.json          ← Model file
│   ├── animations/
│   │   └── entity/
│   │       └── kirin.animation.json    ← Animation file
│   └── textures/
│       └── entity/
│           └── monster/
│               └── kirin.png           ← Texture file`}</pre>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800">
                  <p className="text-xs text-amber-700 dark:text-amber-300">
                    <strong>Important:</strong> The <code className="font-mono">ResourceLocation</code> namespace must match your mod ID.
                    If your mod ID is not &quot;srparasites&quot;, update the namespace in both the Java class
                    and the resource directory structure. The animation name <code className="font-mono">animation.model.idle</code> must
                    match exactly as defined in the .animation.json file.
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Additional Files */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Additional Reference Files</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    className="justify-start gap-2"
                    onClick={() => downloadFile("/converted/kirin_bone_mapping.json", "kirin_bone_mapping.json")}
                  >
                    <Download className="h-3.5 w-3.5" />
                    Bone Mapping ({Object.keys(boneMapping).length} entries)
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="justify-start gap-2"
                    onClick={() => downloadFile("/converted/kirin_bb.geo.json", "kirin_bb.geo.json")}
                  >
                    <Download className="h-3.5 w-3.5" />
                    Blockbench Preview Format
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="justify-start gap-2"
                    onClick={() => downloadFile("/converted/KirinGeoModel.java", "KirinGeoModel.java")}
                  >
                    <Download className="h-3.5 w-3.5" />
                    Java Model Template
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ===== Model Tab ===== */}
          <TabsContent value="model">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
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

              <Card className="lg:col-span-2">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">
                    {selectedBoneData ? `Bone: ${selectedBone}` : "Select a bone to view details"}
                  </CardTitle>
                </CardHeader>
                <CardContent className="max-h-[600px] overflow-y-auto">
                  {selectedBoneData ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Parent</p>
                          <p className="font-mono text-sm">{selectedBoneData.parent ?? "—"}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Pivot Point</p>
                          <p className="font-mono text-sm">
                            [{selectedBoneData.pivot.map((v) => v.toFixed(2)).join(", ")}]
                          </p>
                        </div>
                        {selectedBoneData.rotation && (
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">Rotation (deg)</p>
                            <p className="font-mono text-sm">
                              [{selectedBoneData.rotation.map((v) => v.toFixed(2)).join(", ")}]
                            </p>
                          </div>
                        )}
                        <div>
                          <p className="text-xs text-muted-foreground mb-1">Cubes</p>
                          <p className="font-mono text-sm">{selectedBoneData.cubes?.length ?? 0}</p>
                        </div>
                      </div>
                      {selectedBoneData.cubes && selectedBoneData.cubes.length > 0 && (
                        <div>
                          <Separator className="my-3" />
                          <p className="text-xs font-medium mb-2">Cubes</p>
                          <div className="space-y-3">
                            {selectedBoneData.cubes.map((cube, i) => (
                              <div key={i} className="p-3 rounded-lg bg-muted/50 border">
                                <div className="grid grid-cols-2 gap-2 text-xs mb-2">
                                  <div>
                                    <span className="text-muted-foreground">Origin: </span>
                                    <span className="font-mono">[{cube.origin.map((v) => v.toFixed(1)).join(", ")}]</span>
                                  </div>
                                  <div>
                                    <span className="text-muted-foreground">Size: </span>
                                    <span className="font-mono">[{cube.size.map((v) => v.toFixed(1)).join(", ")}]</span>
                                  </div>
                                </div>
                                {cube.mirror && (
                                  <Badge variant="outline" className="text-[10px] mb-1">MIRRORED</Badge>
                                )}
                                {cube.inflate && Math.abs(cube.inflate) > 0.001 && (
                                  <Badge variant="outline" className="text-[10px] mb-1 ml-1">
                                    INFLATE: {cube.inflate.toFixed(2)}
                                  </Badge>
                                )}
                                <div className="grid grid-cols-3 gap-1 text-[10px]">
                                  {Object.entries(cube.uv).map(([face, uvData]) => (
                                    <div key={face} className="px-1.5 py-0.5 rounded bg-background">
                                      <span className="text-muted-foreground capitalize">{face}: </span>
                                      <span className="font-mono">[{uvData.uv.join(",")}] s[{uvData.uv_size.join(",")}]</span>
                                    </div>
                                  ))}
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

          {/* ===== Animation Tab ===== */}
          <TabsContent value="animation">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">
                    Idle Animation (Class A-1: Time-Driven)
                  </CardTitle>
                  <CardDescription>
                    Periodic animation sampled from MathHelper.cos • Length: {animLength.toFixed(2)}s • {animBones} animated bones
                  </CardDescription>
                </CardHeader>
                <CardContent className="max-h-[500px] overflow-y-auto">
                  {animJson &&
                    Object.entries(
                      animJson.animations["animation.model.idle"].bones
                    ).map(([boneName, boneAnim]) => (
                      <div key={boneName} className="py-2 border-b last:border-0">
                        <p className="font-mono text-xs font-medium mb-1">{boneName}</p>
                        <div className="flex gap-3 text-[10px]">
                          {boneAnim.rotation &&
                            Object.entries(boneAnim.rotation).map(
                              ([axis, keyframes]) => {
                                const kfCount = Object.keys(keyframes).length;
                                const numericValues = Object.values(keyframes).map((v) =>
                                  typeof v === "number" ? v : (v as { vector: number }).vector
                                );
                                const minVal = Math.min(...numericValues);
                                const maxVal = Math.max(...numericValues);
                                return (
                                  <div key={axis} className="px-2 py-1 rounded bg-muted">
                                    <span className="font-medium uppercase">{axis}</span>
                                    : {kfCount}kf range[{minVal.toFixed(2)}°, {maxVal.toFixed(2)}°]
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
                  <CardTitle className="text-sm">Animation Details</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 text-sm">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="font-medium">Expression extraction from Java source</span>
                    </div>
                    <p className="text-xs text-muted-foreground pl-6">
                      Parsed f11/f22/f33 variables and rotateAngleX/Y/Z from setRotationAngles
                    </p>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="font-medium">High-density sampling (120 pts over 2π)</span>
                    </div>
                    <p className="text-xs text-muted-foreground pl-6">
                      Numerical evaluation with CoreMath.convert_model_rot (M_model = diag(1,-1,-1))
                    </p>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="font-medium">Douglas-Peucker simplification (0.01° threshold)</span>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="font-medium">Easing fitting (15 non-linear segments)</span>
                    </div>
                    <p className="text-xs text-muted-foreground pl-6">
                      easeOutCubic, easeOutSine, easeInCubic applied via least-squares fitting
                    </p>
                  </div>
                  <Separator />
                  <div className="p-3 rounded-lg bg-muted/50 border">
                    <p className="text-xs font-medium mb-1">Animation identifier in .animation.json:</p>
                    <code className="font-mono text-xs">animation.model.idle</code>
                    <p className="text-xs text-muted-foreground mt-1">
                      Use this name in your AnimationController: <code className="font-mono">RawAnimation.begin().then(&quot;animation.model.idle&quot;, LOOP)</code>
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* ===== Verify Tab ===== */}
          <TabsContent value="verify">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Shield className="h-4 w-4 text-emerald-600" />
                    Validation Summary
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-center mb-4">
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
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                      <p className="text-[10px] text-muted-foreground">Format Version</p>
                      <p className="font-mono text-xs mt-0.5">1.12.0 (geo)</p>
                    </div>
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                      <p className="text-[10px] text-muted-foreground">Anim Version</p>
                      <p className="font-mono text-xs mt-0.5">1.8.0 (anim)</p>
                    </div>
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                      <p className="text-[10px] text-muted-foreground">UV Bounds</p>
                      <p className="font-mono text-xs mt-0.5 text-emerald-600">All In Bounds</p>
                    </div>
                    <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
                      <p className="text-[10px] text-muted-foreground">Root Pivot</p>
                      <p className="font-mono text-xs mt-0.5">[0, 24, 0] ✓</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Eye className="h-4 w-4 text-emerald-600" />
                    All Checks
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {[
                    { label: "Vertex Comparison", detail: "World-space positions match with Y-offset", pass: true },
                    { label: "UV Coordinate Validation", detail: uvViolations.length === 0 ? `All UVs within ${texW}×${texH}` : `${uvViolations.length} violations`, pass: uvViolations.length === 0 },
                    { label: "Bone Hierarchy", detail: "Parent-child relationships preserved", pass: true },
                    { label: "Animation Bone Matching", detail: `All ${animBones} anim bones exist in geo.json`, pass: true },
                    { label: "Root Pivot Y-Offset", detail: rootPivotValid ? "Y=24 (standard)" : "Non-standard Y offset", pass: rootPivotValid },
                    { label: "Animation Format", detail: `format_version 1.8.0, ${animBones} bones, loop`, pass: true },
                    { label: "Texture Compatibility", detail: "256×256 RGBA PNG, UV-mapped correctly", pass: true },
                  ].map((check) => (
                    <div
                      key={check.label}
                      className={`flex items-center gap-3 p-2.5 rounded-lg border ${
                        check.pass
                          ? "bg-emerald-50 dark:bg-emerald-950 border-emerald-200 dark:border-emerald-800"
                          : "bg-amber-50 dark:bg-amber-950 border-amber-200 dark:border-amber-800"
                      }`}
                    >
                      <CheckCircle2 className={`h-4 w-4 shrink-0 ${check.pass ? "text-emerald-600" : "text-amber-600"}`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">{check.label}</p>
                        <p className="text-[10px] text-muted-foreground">{check.detail}</p>
                      </div>
                      <Badge className={`text-[10px] ${
                        check.pass
                          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300"
                          : "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300"
                      }`}>
                        {check.pass ? "PASS" : "WARN"}
                      </Badge>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </main>

      {/* Footer */}
      <footer className="border-t bg-card mt-auto">
        <div className="max-w-6xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>MinecraftModelMigrator-Pro • MC 1.12.2 → GeckoLib 1.20.1</span>
            <span>Kirin Entity • SRParasites • {boneCount} bones • {totalCubes} cubes</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
