import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

// ─── Types ──────────────────────────────────────────────────────────────────

interface CreatureEntry {
  id: string;
  nameZh: string;
  nameEn: string;
  category: string;
  hasBbmodel: boolean;
  fileSize: number;
}

interface CategoryInfo {
  id: string;
  nameZh: string;
  nameEn: string;
  creatures: CreatureEntry[];
}

interface CreaturesResponse {
  categories: CategoryInfo[];
  totalModels: number;
  totalSize: number;
}

// ─── Category names ────────────────────────────────────────────────────────

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
  abomination: { zh: "憎恶种", en: "Abomination" },
  projectile: { zh: "抛射物", en: "Projectile" },
  misc: { zh: "其他", en: "Misc" },
};

// ─── Creature names ────────────────────────────────────────────────────────
// Merged from zh_cn.lang item spawner names + all MDO-SRP model IDs

const CREATURE_NAMES: Record<string, { zh: string; en: string }> = {
  // ── Inborn (先天种) ──
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

  // ── Deterrent (威慑种) ──
  venkrol: { zh: "I阶召唤柱", en: "Venkrol S-I" },
  venkrolSII: { zh: "II阶召唤柱", en: "Venkrol S-II" },
  venkrolsii: { zh: "II阶召唤柱(变体)", en: "Venkrol S-II var" },
  venkrolSIII: { zh: "III阶召唤柱", en: "Venkrol S-III" },
  venkrolsiii: { zh: "III阶召唤柱(变体)", en: "Venkrol S-III var" },
  venkrolSIV: { zh: "IV阶召唤柱", en: "Venkrol S-IV" },
  venkrolsiv: { zh: "IV阶召唤柱(变体)", en: "Venkrol S-IV var" },
  venkrolSV: { zh: "V阶召唤柱", en: "Venkrol S-V" },
  venkrolsv: { zh: "V阶召唤柱(变体)", en: "Venkrol S-V var" },
  dod: { zh: "I阶调度柱", en: "DoD S-I" },
  dodSII: { zh: "II阶调度柱", en: "DoD S-II" },
  dodsii: { zh: "II阶调度柱(变体)", en: "DoD S-II var" },
  dodSIII: { zh: "III阶调度柱", en: "DoD S-III" },
  dodsiii: { zh: "III阶调度柱(变体)", en: "DoD S-III var" },
  dodSIV: { zh: "IV阶调度柱", en: "DoD S-IV" },
  dodsiv: { zh: "IV阶调度柱(变体)", en: "DoD S-IV var" },
  dodSIVH: { zh: "IV阶调度柱-H", en: "DoD S-IVH" },
  dodsivh: { zh: "IV阶调度柱-H(变体)", en: "DoD S-IVH var" },
  dodT: { zh: "调度塔", en: "DoD Tower" },
  dodt: { zh: "调度塔(变体)", en: "DoD Tower var" },
  leem: { zh: "I阶支庇柱", en: "Leem S-I" },
  leemB: { zh: "支庇柱-B", en: "Leem-B" },
  leemb: { zh: "支庇柱-B(变体)", en: "Leem-B var" },
  leemSII: { zh: "II阶支庇柱", en: "Leem S-II" },
  leemsii: { zh: "II阶支庇柱(变体)", en: "Leem S-II var" },
  leemSIII: { zh: "III阶支庇柱", en: "Leem S-III" },
  leemsiii: { zh: "III阶支庇柱(变体)", en: "Leem S-III var" },
  leemSIV: { zh: "IV阶支庇柱", en: "Leem S-IV" },
  leemsiv: { zh: "IV阶支庇柱(变体)", en: "Leem S-IV var" },
  unvo: { zh: "哨戒爪", en: "Sentry" },
  nak: { zh: "缠缚触手", en: "Nak" },
  rof: { zh: "熔渊体", en: "Rof" },
  tonro: { zh: "曲击柱", en: "Tonro" },

  // ── Derived (衍生种) ──
  heblu: { zh: "邪狱龙", en: "Heblu" },
  kirin: { zh: "踏虚体", en: "Kirin" },

  // ── Primitive (原始种) ──
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

  // ── Adapted (适应种) ──
  banoAdapted: { zh: "适应巴诺", en: "Bano Adapted" },
  canraAdapted: { zh: "适应坎拉", en: "Canra Adapted" },
  emanaAdapted: { zh: "适应艾玛纳", en: "Emana Adapted" },
  gimAdapted: { zh: "适应金姆", en: "Gim Adapted" },
  hullAdapted: { zh: "适应赫尔", en: "Hull Adapted" },
  ikiAdapted: { zh: "适应伊基", en: "Iki Adapted" },
  lumAdapted: { zh: "适应卢姆", en: "Lum Adapted" },
  noglaAdapted: { zh: "适应诺格拉", en: "Nogla Adapted" },
  ranracAdapted: { zh: "适应兰拉克", en: "Ranrac Adapted" },
  shycoAdapted: { zh: "适应夏科", en: "Shyco Adapted" },
  wymoAdapted: { zh: "适应威莫", en: "Wymo Adapted" },
  zaaAdapted: { zh: "适应扎", en: "Zaa Adapted" },

  // ── Pure (纯粹种) ──
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

  // ── Ancient (远古种) ──
  terla: { zh: "特拉", en: "Terla" },
  oronco: { zh: "奥隆科", en: "Oronco" },
  oroncoTen: { zh: "奥隆科-天", en: "Oronco Ten" },

  // ── Awakened (觉醒种) ──
  oroncoAW: { zh: "觉醒奥隆科", en: "Oronco AW" },
  oroncoAWFL: { zh: "觉醒奥隆科-飞行", en: "Oronco AW Flight" },

  // ── Feral (狂化种) ──
  ferBear: { zh: "狂化熊", en: "Feral Bear" },
  ferCow: { zh: "狂化牛", en: "Feral Cow" },
  ferEnderman: { zh: "狂化末影人", en: "Feral Enderman" },
  ferHorse: { zh: "狂化马", en: "Feral Horse" },
  ferHuman: { zh: "狂化人类", en: "Feral Human" },
  ferPig: { zh: "狂化猪", en: "Feral Pig" },
  ferSheep: { zh: "狂化羊", en: "Feral Sheep" },
  ferVillager: { zh: "狂化村民", en: "Feral Villager" },
  ferWolf: { zh: "狂化狼", en: "Feral Wolf" },

  // ── Crude (粗制种) ──
  cruxA: { zh: "十字-A", en: "Crux A" },
  cruxB: { zh: "十字-B", en: "Crux B" },
  done: { zh: "顿", en: "Done" },
  heed: { zh: "希德", en: "Heed" },
  host: { zh: "宿主", en: "Host" },
  hostII: { zh: "II阶宿主", en: "Host S-II" },
  inhooM: { zh: "印胡-M", en: "Inhoo M" },
  inhooS: { zh: "印胡-S", en: "Inhoo S" },
  leer: { zh: "利尔", en: "Leer" },
  mes: { zh: "梅斯", en: "Mes" },
  quac: { zh: "夸克", en: "Quac" },

  // ── Infected (感染种) ──
  dorpa: { zh: "多尔帕", en: "Dorpa" },
  infBear: { zh: "感染熊", en: "Infected Bear" },
  infCow: { zh: "感染牛", en: "Infected Cow" },
  infCowHead: { zh: "感染牛头", en: "Infected Cow Head" },
  infDragonE: { zh: "感染末影龙", en: "Infected Dragon E" },
  infDragonEHead: { zh: "感染末影龙头", en: "Infected Dragon E Head" },
  infEnderman: { zh: "感染末影人", en: "Infected Enderman" },
  infEndermanHead: { zh: "感染末影人头", en: "Infected Enderman Head" },
  infHorse: { zh: "感染马", en: "Infected Horse" },
  infHorseHead: { zh: "感染马头", en: "Infected Horse Head" },
  infHuman: { zh: "感染人类", en: "Infected Human" },
  infHumanHead: { zh: "感染人类头", en: "Infected Human Head" },
  infPig: { zh: "感染猪", en: "Infected Pig" },
  infPigHead: { zh: "感染猪头", en: "Infected Pig Head" },
  infPlayer: { zh: "感染玩家", en: "Infected Player" },
  infPlayerHead: { zh: "感染玩家头", en: "Infected Player Head" },
  infSheep: { zh: "感染羊", en: "Infected Sheep" },
  infSheepHead: { zh: "感染羊头", en: "Infected Sheep Head" },
  infSquid: { zh: "感染鱿鱼", en: "Infected Squid" },
  infVillager: { zh: "感染村民", en: "Infected Villager" },
  infVillagerHead: { zh: "感染村民头", en: "Infected Villager Head" },
  infWolf: { zh: "感染狼", en: "Infected Wolf" },
  infWolfHead: { zh: "感染狼头", en: "Infected Wolf Head" },
  speBear: { zh: "特种熊", en: "Special Bear" },
  speCow: { zh: "特种牛", en: "Special Cow" },
  speEnderman: { zh: "特种末影人", en: "Special Enderman" },
  speHuman: { zh: "特种人类", en: "Special Human" },
  speSheep: { zh: "特种羊", en: "Special Sheep" },
  speVillager: { zh: "特种村民", en: "Special Villager" },

  // ── Hijacked (劫持种) ──
  hiBlaze: { zh: "劫持烈焰人", en: "Hijacked Blaze" },
  hiGolem: { zh: "劫持铁傀儡", en: "Hijacked Golem" },
  hiSkeleton: { zh: "劫持骷髅", en: "Hijacked Skeleton" },

  // ── Focused (聚焦种) ──
  banoFocused: { zh: "聚焦巴诺", en: "Bano Focused" },
  shycoFocused: { zh: "聚焦夏科", en: "Shyco Focused" },

  // ── Abomination (憎恶种) ──
  aboBodies: { zh: "憎恶体", en: "Abomination Bodies" },
  aboHead: { zh: "憎恶头", en: "Abomination Head" },

  // ── Projectile (抛射物) ──
  dropPod: { zh: "空降舱", en: "Drop Pod" },

  // ── Misc (其他) ──
  biomassPod: { zh: "生物质舱", en: "Biomass Pod" },
  biomassVenkrol: { zh: "生物质召唤柱", en: "Biomass Venkrol" },
  bombHost: { zh: "宿主炸弹", en: "Host Bomb" },
  bombJinjo: { zh: "金乔炸弹", en: "Jinjo Bomb" },
  bombOmboo: { zh: "翁布炸弹", en: "Omboo Bomb" },
  gore: { zh: "血肉块", en: "Gore" },
  meteor: { zh: "陨石", en: "Meteor" },
  nULL: { zh: "虚无", en: "NULL" },
  nade: { zh: "手雷", en: "Grenade" },
  orbScary: { zh: "恐惧球", en: "Scary Orb" },
  orbVoid: { zh: "虚空球", en: "Void Orb" },
  projectileHomming: { zh: "追踪弹", en: "Homing Projectile" },
  tendrilAnged: { zh: "安格德触须", en: "Anged Tendril" },
  tendrilBano: { zh: "巴诺触须", en: "Bano Tendril" },
  tendrilCanra: { zh: "坎拉触须", en: "Canra Tendril" },
  tendrilDragonELW: { zh: "末影龙触须-LW", en: "Dragon E Tendril LW" },
  tendrilDragonERW: { zh: "末影龙触须-RW", en: "Dragon E Tendril RW" },
  tendrilEsor: { zh: "埃索触须", en: "Esor Tendril" },
  tendrilNogla: { zh: "诺格拉触须", en: "Nogla Tendril" },
  tendrilShyco: { zh: "夏科触须", en: "Shyco Tendril" },
};

// ─── Config ────────────────────────────────────────────────────────────────

const MDO_SRP_DIR = "/home/z/my-project/MDO-SRP";

const CATEGORY_ORDER = [
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

// ─── Route Handler ─────────────────────────────────────────────────────────

export async function GET() {
  try {
    const categories: CategoryInfo[] = [];
    let totalModels = 0;
    let totalSize = 0;

    if (!fs.existsSync(MDO_SRP_DIR)) {
      return NextResponse.json(
        { error: "MDO-SRP directory not found" },
        { status: 500 }
      );
    }

    for (const catId of CATEGORY_ORDER) {
      const catDir = path.join(MDO_SRP_DIR, catId);
      if (!fs.existsSync(catDir)) continue;

      const catInfo = CATEGORY_NAMES[catId] || { zh: catId, en: catId };
      const creatures: CreatureEntry[] = [];

      // Scan for .bbmodel files
      const files = fs.readdirSync(catDir);
      const bbmodelFiles = files.filter((f) => f.endsWith(".bbmodel"));

      for (const bbmodelFile of bbmodelFiles) {
        const id = bbmodelFile.replace(".bbmodel", "");
        const filePath = path.join(catDir, bbmodelFile);
        const stat = fs.statSync(filePath);
        const names = CREATURE_NAMES[id] || { zh: id, en: id };

        creatures.push({
          id,
          nameZh: names.zh,
          nameEn: names.en,
          category: catId,
          hasBbmodel: true,
          fileSize: stat.size,
        });

        totalSize += stat.size;
      }

      if (creatures.length > 0) {
        // Sort creatures by id for consistent ordering
        creatures.sort((a, b) => a.id.localeCompare(b.id));
        categories.push({
          id: catId,
          nameZh: catInfo.zh,
          nameEn: catInfo.en,
          creatures,
        });
        totalModels += creatures.length;
      }
    }

    const response: CreaturesResponse = {
      categories,
      totalModels,
      totalSize,
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("Failed to list creatures:", error);
    return NextResponse.json(
      { error: "Failed to list creatures" },
      { status: 500 }
    );
  }
}
