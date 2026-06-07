import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

// Category definitions matching the lang file (zh_cn.lang)
// tier.srparasites.inborn=先天种, deterrent=威慑种, derived=衍生种, etc.
interface CreatureEntry {
  id: string;
  nameZh: string;
  nameEn: string;
  category: string;
  hasGeo: boolean;
  hasAnimation: boolean;
  hasTexture: boolean;
}

interface CategoryInfo {
  id: string;
  nameZh: string;
  nameEn: string;
  creatures: CreatureEntry[];
}

// Chinese category names from zh_cn.lang
const CATEGORY_NAMES: Record<string, { zh: string; en: string }> = {
  inborn: { zh: "先天种", en: "Inborn" },
  deterrent: { zh: "威慑种", en: "Deterrent" },
  derived: { zh: "衍生种", en: "Derived" },
  primitive: { zh: "原始种", en: "Primitive" },
  adapted: { zh: "适应种", en: "Adapted" },
  pure: { zh: "纯粹种", en: "Pure" },
  ancient: { zh: "远古种", en: "Ancient" },
  awakened: { zh: "觉醒种", en: "Awakened" },
  feral: { zh: "狂化种", en: "Feral" },
  crude: { zh: "粗制种", en: "Crude" },
  infected: { zh: "感染种", en: "Infected" },
  hijacked: { zh: "劫持种", en: "Hijacked" },
  focused: { zh: "聚焦种", en: "Focused" },
  misc: { zh: "其他", en: "Misc" },
  abomination: { zh: "憎恶种", en: "Abomination" },
  projectile: { zh: "抛射物", en: "Projectile" },
};

// Chinese creature names from zh_cn.lang (item spawner names, more reliable)
const CREATURE_NAMES: Record<string, { zh: string; en: string }> = {
  // Inborn (先天种)
  ata: { zh: "狂疫虫", en: "Gnat" },
  kol: { zh: "蛹兽", en: "Kol" },
  viin: { zh: "钳兽", en: "Viin" },
  buthol: { zh: "飞行母体", en: "Buthol" },
  rathol: { zh: "重型母体", en: "Rathol" },
  gothol: { zh: "轻型母体", en: "Gothol" },
  lesh: { zh: "活体肉块", en: "Lesh" },
  lodo: { zh: "虫灵", en: "Lodo" },
  nuuh: { zh: "凶裂兽", en: "Nuuh" },
  mudo: { zh: "裂兽", en: "Mudo" },
  mor: { zh: "墨兽", en: "Mor" },
  // Deterrent (威慑种)
  venkrol: { zh: "I阶召唤柱", en: "Venkrol S-I" },
  venkrolSII: { zh: "II阶召唤柱", en: "Venkrol S-II" },
  venkrolSIII: { zh: "III阶召唤柱", en: "Venkrol S-III" },
  venkrolSIV: { zh: "IV阶召唤柱", en: "Venkrol S-IV" },
  venkrolSV: { zh: "V阶召唤柱", en: "Venkrol S-V" },
  dod: { zh: "I阶调度柱", en: "DoD S-I" },
  dodSII: { zh: "II阶调度柱", en: "DoD S-II" },
  dodSIII: { zh: "III阶调度柱", en: "DoD S-III" },
  dodSIV: { zh: "IV阶调度柱", en: "DoD S-IV" },
  dodSIVH: { zh: "IV阶调度柱-H", en: "DoD S-IVH" },
  dodT: { zh: "调度塔", en: "DoD Tower" },
  leem: { zh: "I阶支庇柱", en: "Leem S-I" },
  leemB: { zh: "支庇柱-B", en: "Leem-B" },
  leemSII: { zh: "II阶支庇柱", en: "Leem S-II" },
  leemSIII: { zh: "III阶支庇柱", en: "Leem S-III" },
  leemSIV: { zh: "IV阶支庇柱", en: "Leem S-IV" },
  unvo: { zh: "哨戒爪", en: "Sentry" },
  nak: { zh: "缠缚触手", en: "Nak" },
  rof: { zh: "熔渊体", en: "Rof" },
  tonro: { zh: "曲击柱", en: "Tonro" },
  // Derived (衍生种)
  heblu: { zh: "邪狱龙", en: "Heblu" },
  kirin: { zh: "踏虚体", en: "Kirin" },
  // Primitive (原始种)
  bano: { zh: "巴诺", en: "Bano" },
  canra: { zh: "坎拉", en: "Canra" },
  emana: { zh: "艾玛纳", en: "Emana" },
  gim: { zh: "金姆", en: "Gim" },
  hull: { zh: "赫尔", en: "Hull" },
  iki: { zh: "伊基", en: "Iki" },
  lum: { zh: "卢姆", en: "Lum" },
  nogla: { zh: "诺格拉", en: "Nogla" },
  ranrac: { zh: "兰拉克", en: "Ranrac" },
  shyco: { zh: "夏科", en: "Shyco" },
  wymo: { zh: "威莫", en: "Wymo" },
  zaa: { zh: "扎", en: "Zaa" },
  // Pure (纯粹种)
  alafha: { zh: "阿拉法", en: "Alafha" },
  anged: { zh: "安格德", en: "Anged" },
  elvia: { zh: "艾尔维亚", en: "Elvia" },
  esor: { zh: "埃索", en: "Esor" },
  flam: { zh: "弗拉姆", en: "Flam" },
  flog: { zh: "弗洛格", en: "Flog" },
  ganro: { zh: "甘罗", en: "Ganro" },
  jinjo: { zh: "金乔", en: "Jinjo" },
  lencia: { zh: "伦西亚", en: "Lencia" },
  omboo: { zh: "翁布", en: "Omboo" },
  orch: { zh: "奥克", en: "Orch" },
  pheon: { zh: "菲昂", en: "Pheon" },
  rond: { zh: "隆德", en: "Rond" },
  tenn: { zh: "坦恩", en: "Tenn" },
  vesta: { zh: "维斯塔", en: "Vesta" },
};

const OUTPUT_DIR = path.join(process.cwd(), "db", "output");

export async function GET() {
  try {
    const categories: CategoryInfo[] = [];
    const categoryOrder = [
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

    for (const catId of categoryOrder) {
      const catDir = path.join(OUTPUT_DIR, catId);
      if (!fs.existsSync(catDir)) continue;

      const catInfo = CATEGORY_NAMES[catId] || { zh: catId, en: catId };
      const creatures: CreatureEntry[] = [];

      // Get unique model names from geo.json files (authoritative source)
      const files = fs.readdirSync(catDir);
      const geoFiles = files.filter((f) => f.endsWith(".geo.json"));

      for (const geoFile of geoFiles) {
        const id = geoFile.replace(".geo.json", "");
        const hasAnimation = files.includes(`${id}.animation.json`);
        const hasTexture = files.includes(`${id}.png`);
        const names = CREATURE_NAMES[id] || { zh: id, en: id };

        creatures.push({
          id,
          nameZh: names.zh,
          nameEn: names.en,
          category: catId,
          hasGeo: true,
          hasAnimation,
          hasTexture,
        });
      }

      if (creatures.length > 0) {
        categories.push({
          id: catId,
          nameZh: catInfo.zh,
          nameEn: catInfo.en,
          creatures,
        });
      }
    }

    return NextResponse.json({ categories });
  } catch (error) {
    console.error("Failed to list creatures:", error);
    return NextResponse.json(
      { error: "Failed to list creatures" },
      { status: 500 }
    );
  }
}
