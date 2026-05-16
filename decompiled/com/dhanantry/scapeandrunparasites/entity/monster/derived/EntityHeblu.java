/*
 * Decompiled with CFR 0.152.
 * 
 * Could not load the following classes:
 *  javax.annotation.Nonnull
 *  net.minecraft.block.Block
 *  net.minecraft.entity.Entity
 *  net.minecraft.entity.EntityCreature
 *  net.minecraft.entity.EntityLiving
 *  net.minecraft.entity.EntityLivingBase
 *  net.minecraft.entity.IEntityLivingData
 *  net.minecraft.entity.IRangedAttackMob
 *  net.minecraft.entity.MoverType
 *  net.minecraft.entity.SharedMonsterAttributes
 *  net.minecraft.entity.ai.EntityAIBase
 *  net.minecraft.entity.ai.EntityAIHurtByTarget
 *  net.minecraft.entity.ai.EntityMoveHelper
 *  net.minecraft.entity.ai.EntityMoveHelper$Action
 *  net.minecraft.entity.player.EntityPlayer
 *  net.minecraft.init.Blocks
 *  net.minecraft.init.SoundEvents
 *  net.minecraft.nbt.NBTTagCompound
 *  net.minecraft.network.datasync.DataParameter
 *  net.minecraft.network.datasync.DataSerializer
 *  net.minecraft.network.datasync.DataSerializers
 *  net.minecraft.network.datasync.EntityDataManager
 *  net.minecraft.potion.PotionEffect
 *  net.minecraft.util.DamageSource
 *  net.minecraft.util.EnumParticleTypes
 *  net.minecraft.util.SoundEvent
 *  net.minecraft.util.math.BlockPos
 *  net.minecraft.util.math.MathHelper
 *  net.minecraft.util.math.Vec3d
 *  net.minecraft.world.DifficultyInstance
 *  net.minecraft.world.World
 *  net.minecraftforge.fml.relauncher.Side
 *  net.minecraftforge.fml.relauncher.SideOnly
 */
package com.dhanantry.scapeandrunparasites.entity.monster.derived;

import com.dhanantry.scapeandrunparasites.client.particle.SRPEnumParticle;
import com.dhanantry.scapeandrunparasites.entity.EntityBody;
import com.dhanantry.scapeandrunparasites.entity.EntityToxicCloud;
import com.dhanantry.scapeandrunparasites.entity.ai.EntityAIAttackMeleeRangeSwitch;
import com.dhanantry.scapeandrunparasites.entity.ai.EntityAIAttackMeleeStatusAOE;
import com.dhanantry.scapeandrunparasites.entity.ai.EntityAIAttackRangedStatus;
import com.dhanantry.scapeandrunparasites.entity.ai.EntityAIFlightAttack;
import com.dhanantry.scapeandrunparasites.entity.ai.EntityAISwimmingDiving;
import com.dhanantry.scapeandrunparasites.entity.ai.misc.EntityBodyParts;
import com.dhanantry.scapeandrunparasites.entity.ai.misc.EntityCanFly;
import com.dhanantry.scapeandrunparasites.entity.ai.misc.EntityCutomAttack;
import com.dhanantry.scapeandrunparasites.entity.ai.misc.EntityPCosmical;
import com.dhanantry.scapeandrunparasites.entity.ai.misc.EntityPDerived;
import com.dhanantry.scapeandrunparasites.entity.projectile.EntityProjectileAlafhaBall;
import com.dhanantry.scapeandrunparasites.init.SRPPotions;
import com.dhanantry.scapeandrunparasites.init.SRPSounds;
import com.dhanantry.scapeandrunparasites.util.SRPAttributes;
import com.dhanantry.scapeandrunparasites.util.config.SRPConfig;
import javax.annotation.Nonnull;
import net.minecraft.block.Block;
import net.minecraft.entity.Entity;
import net.minecraft.entity.EntityCreature;
import net.minecraft.entity.EntityLiving;
import net.minecraft.entity.EntityLivingBase;
import net.minecraft.entity.IEntityLivingData;
import net.minecraft.entity.IRangedAttackMob;
import net.minecraft.entity.MoverType;
import net.minecraft.entity.SharedMonsterAttributes;
import net.minecraft.entity.ai.EntityAIBase;
import net.minecraft.entity.ai.EntityAIHurtByTarget;
import net.minecraft.entity.ai.EntityMoveHelper;
import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.init.Blocks;
import net.minecraft.init.SoundEvents;
import net.minecraft.nbt.NBTTagCompound;
import net.minecraft.network.datasync.DataParameter;
import net.minecraft.network.datasync.DataSerializer;
import net.minecraft.network.datasync.DataSerializers;
import net.minecraft.network.datasync.EntityDataManager;
import net.minecraft.potion.PotionEffect;
import net.minecraft.util.DamageSource;
import net.minecraft.util.EnumParticleTypes;
import net.minecraft.util.SoundEvent;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.MathHelper;
import net.minecraft.util.math.Vec3d;
import net.minecraft.world.DifficultyInstance;
import net.minecraft.world.World;
import net.minecraftforge.fml.relauncher.Side;
import net.minecraftforge.fml.relauncher.SideOnly;

public class EntityHeblu
extends EntityPDerived
implements EntityCutomAttack,
EntityBodyParts,
IRangedAttackMob,
EntityCanFly {
    protected static final DataParameter<Boolean> FLYING = EntityDataManager.func_187226_a(EntityHeblu.class, (DataSerializer)DataSerializers.field_187198_h);
    private int flying;
    private float aaa;
    private float sss;
    private EntityBody leftTendril;
    private EntityBody rightTendril;
    private EntityBody head;
    private float leftTendrilHealth;
    private float rightTendrilHealth;
    private float headlHealth;
    public int vomit;
    private BlockPos vomitPos;
    public boolean raining;
    private int rainingOrbs = 0;
    protected static final DataParameter<Byte> VEX_FLAGS = EntityDataManager.func_187226_a(EntityHeblu.class, (DataSerializer)DataSerializers.field_187191_a);
    private static final DataParameter<Boolean> ATTACKING = EntityDataManager.func_187226_a(EntityHeblu.class, (DataSerializer)DataSerializers.field_187198_h);
    private int limit;
    private boolean skillFlame;
    private double tttX;
    private double tttY;
    private double tttZ;
    private double tttH;
    private double tttHH;

    public EntityHeblu(World worldIn) {
        super(worldIn);
        this.func_70105_a(2.4f, 3.8f);
        this.field_70138_W = 1.0f;
        this.canModRender = 0;
        this.type = (byte)14;
        this.killcount = -10.0;
        this.field_70714_bg.func_85156_a((EntityAIBase)this.folow);
        this.flying = 0;
        this.skillFlame = false;
        this.leftTendril = new EntityBody(this, 3.3f, 2.5f, 1.0f, 4.1f, 3.3f, 1, 1, true);
        this.rightTendril = new EntityBody(this, 3.3f, 2.5f, 1.0f, 4.1f, 3.3f, -1, 2, true);
        this.head = new EntityBody(this, 2.2f, 2.2f, 1.0f, 4.0f, 2.0f, -1, 3, false, 0.2f);
        this.leftTendrilHealth = (float)((double)this.func_110138_aP() * SRPConfig.tendrilHealth);
        this.rightTendrilHealth = (float)((double)this.func_110138_aP() * SRPConfig.tendrilHealth);
        this.headlHealth = (float)((double)this.func_110138_aP() * SRPConfig.tendrilHealth);
        this.field_70158_ak = true;
        this.field_70765_h = new AIMoveControl(this);
    }

    @Override
    public int getParasiteIDRegister() {
        return 309;
    }

    protected void func_184651_r() {
        this.field_70715_bh.func_75776_a(1, (EntityAIBase)new EntityAIHurtByTarget((EntityCreature)this, true, new Class[0]));
        this.field_70714_bg.func_75776_a(0, (EntityAIBase)new EntityAISwimmingDiving((EntityLiving)this, 0.08));
        this.field_70714_bg.func_75776_a(3, (EntityAIBase)new EntityAIAttackMeleeStatusAOE(this, 1.3, false, 8.0, 9.0));
        this.field_70714_bg.func_75776_a(5, (EntityAIBase)new AIMoveRandom());
        this.field_70714_bg.func_75776_a(6, (EntityAIBase)new AIFireballAttack(this));
        this.field_70714_bg.func_75776_a(3, (EntityAIBase)new EntityAIFlightAttack(this, SRPConfig.derivedFollow, true, 3));
        this.field_70714_bg.func_75776_a(6, (EntityAIBase)new EntityAIAttackMeleeRangeSwitch(this, 12.0f));
        this.field_70714_bg.func_75776_a(4, (EntityAIBase)new EntityAIAttackRangedStatus(this, 1.3, 100, 40.0f, false));
    }

    protected void func_110147_ax() {
        super.func_110147_ax();
        this.func_110148_a(SharedMonsterAttributes.field_111267_a).func_111128_a(SRPAttributes.HEBLU_HEALTH);
        this.func_110148_a(SharedMonsterAttributes.field_188791_g).func_111128_a(SRPAttributes.HEBLU_ARMOR);
        this.func_110148_a(SharedMonsterAttributes.field_111263_d).func_111128_a(0.27);
        this.func_110148_a(SharedMonsterAttributes.field_111266_c).func_111128_a(SRPAttributes.HEBLU_KD_RESISTANCE);
        this.func_110148_a(SharedMonsterAttributes.field_111264_e).func_111128_a(SRPAttributes.HEBLU_ATTACK_DAMAGE);
        this.func_110148_a(SharedMonsterAttributes.field_111265_b).func_111128_a(SRPConfig.derivedFollow);
    }

    @Override
    public void func_70636_d() {
        if (this.func_175446_cd()) {
            return;
        }
        super.func_70636_d();
        this.killcount = -10.0;
        if (this.headlHealth > 0.0f) {
            this.head.func_70071_h_();
        }
        if (this.leftTendrilHealth > 0.0f) {
            this.leftTendril.func_70071_h_();
        }
        if (this.rightTendrilHealth > 0.0f) {
            this.rightTendril.func_70071_h_();
        }
        if (!this.field_70170_p.field_72995_K && this.srpTicks == 10) {
            if ((this.field_70170_p.func_180495_p(this.func_180425_c().func_177979_c(1)).func_177230_c() != Blocks.field_150350_a || this.field_70170_p.func_180495_p(this.func_180425_c().func_177979_c(2)).func_177230_c() != Blocks.field_150350_a) && this.getFlyingState() && this.field_70146_Z.nextInt(3) == 0) {
                this.field_70181_x = 0.5;
            }
            if (this.rainingOrbs > 0) {
                --this.rainingOrbs;
                if (this.rainingOrbs <= 15) {
                    double radius = 10.0;
                    double x = this.field_70165_t + (this.field_70146_Z.nextDouble() * 2.0 - 1.0) * radius;
                    double y = this.field_70163_u + 20.0;
                    double z = this.field_70161_v + (this.field_70146_Z.nextDouble() * 2.0 - 1.0) * radius;
                    if (this.func_70638_az() != null && this.field_70146_Z.nextBoolean()) {
                        x = this.func_70638_az().field_70165_t + (this.field_70146_Z.nextDouble() * 2.0 - 1.0) * radius;
                        z = this.func_70638_az().field_70161_v + (this.field_70146_Z.nextDouble() * 2.0 - 1.0) * radius;
                    }
                    BlockPos pos = new BlockPos(x, y, z);
                    EntityProjectileAlafhaBall entitylargefireball = new EntityProjectileAlafhaBall(this.field_70170_p, (EntityLivingBase)this, 0.0, -10.0, 0.0);
                    entitylargefireball.field_70165_t = x;
                    entitylargefireball.field_70163_u = y;
                    entitylargefireball.field_70161_v = z;
                    this.field_70170_p.func_72838_d((Entity)entitylargefireball);
                }
            }
            if (this.field_70146_Z.nextInt(25) == 0 && !this.getFlyingState() && this.vomit <= 0) {
                this.changeStateTo(true);
                return;
            }
        }
        if (this.vomit > 0) {
            if (!this.field_70170_p.field_72995_K) {
                this.lookAt(this.vomitPos.func_177958_n(), this.vomitPos.func_177956_o(), this.vomitPos.func_177952_p());
            }
            --this.vomit;
            if (this.field_70170_p.field_72995_K) {
                for (int i = 0; i < 19; ++i) {
                    Vec3d vec3d = this.func_70676_i(1.0f);
                    double bon = 8.2;
                    double offsetX = this.field_70165_t + vec3d.field_72450_a * bon;
                    double offsetY = this.field_70163_u + (double)this.func_70047_e() + 2.2;
                    double offsetZ = this.field_70161_v + vec3d.field_72449_c * bon;
                    if (this.raining) {
                        if (this.getFlyingState()) {
                            bon = 4.3;
                            offsetX = this.field_70165_t + vec3d.field_72450_a * bon;
                            offsetY = this.field_70163_u + (double)this.func_70047_e() + 7.5;
                            offsetZ = this.field_70161_v + vec3d.field_72449_c * bon;
                        } else {
                            bon = 6.1;
                            offsetX = this.field_70165_t + vec3d.field_72450_a * bon;
                            offsetY = this.field_70163_u + (double)this.func_70047_e() + 7.2;
                            offsetZ = this.field_70161_v + vec3d.field_72449_c * bon;
                        }
                    }
                    double motionX = (double)(-MathHelper.func_76126_a((float)(this.field_70177_z * (float)Math.PI / 180.0f))) * 1.4;
                    double motionZ = (double)MathHelper.func_76134_b((float)(this.field_70177_z * (float)Math.PI / 180.0f)) * 1.4;
                    double motionY = -0.55 + this.field_70146_Z.nextDouble() * 0.5;
                    double spreadFactor = 0.55;
                    motionX += (this.field_70146_Z.nextDouble() - 0.5) * spreadFactor;
                    motionZ += (this.field_70146_Z.nextDouble() - 0.5) * spreadFactor;
                    double rain = 1.0;
                    if (this.raining) {
                        motionY = 4.5 + this.field_70146_Z.nextDouble() * 0.3;
                        spreadFactor = 0.2;
                        motionX += (this.field_70146_Z.nextDouble() - 0.5) * spreadFactor;
                        motionZ += (this.field_70146_Z.nextDouble() - 0.5) * spreadFactor;
                        rain = 0.2;
                    }
                    this.spawnParticles(EnumParticleTypes.FLAME, offsetX, offsetY, offsetZ, motionX * rain, motionY * rain, motionZ * rain);
                    this.spawnParticles(SRPEnumParticle.GCLOUD, -255, 0, 0, offsetX, offsetY, offsetZ, motionX * rain, motionY * rain, motionZ * rain);
                }
            }
        } else {
            this.raining = false;
        }
        if (this.flying >= 1) {
            ++this.flying;
        }
        if (this.getFlyingState()) {
            this.aaa += 0.08f;
            this.sss += 0.782f;
            if (this.sss >= 24.0f) {
                this.func_184185_a(SoundEvents.field_187524_aN, 5.0f, 0.8f + this.field_70146_Z.nextFloat() * 0.3f);
                this.sss = 0.0f;
            }
            if (this.field_70122_E && !this.field_70170_p.field_72995_K && this.flying > 40) {
                this.changeStateTo(false);
            }
        } else {
            this.aaa = 0.08f;
            this.sss = 0.0f;
        }
    }

    public void func_70071_h_() {
        super.func_70071_h_();
        if (this.getFlyingState()) {
            this.func_189654_d(true);
        } else {
            this.func_189654_d(false);
        }
    }

    public void func_82196_d(EntityLivingBase target, float distanceFactor) {
        this.field_70708_bq = 0;
        this.vomitPos = target.func_180425_c();
        if (target.field_70163_u > this.field_70163_u + 5.0 || target.field_70163_u < this.field_70163_u) {
            double d1 = 4.0;
            Vec3d vec3d = this.func_70676_i(1.0f);
            double d2 = target.field_70165_t - (this.field_70165_t + vec3d.field_72450_a * 4.0);
            double d3 = target.func_174813_aQ().field_72338_b + (double)(target.field_70131_O / 2.0f) - (0.5 + this.field_70163_u + (double)(this.field_70131_O / 2.0f));
            double d4 = target.field_70161_v - (this.field_70161_v + vec3d.field_72449_c * 4.0);
            this.field_70170_p.func_180498_a((EntityPlayer)null, 1016, this.func_180425_c(), 0);
            EntityProjectileAlafhaBall entitylargefireball = new EntityProjectileAlafhaBall(this.field_70170_p, (EntityLivingBase)this, d2, d3, d4);
            entitylargefireball.field_70165_t = this.field_70165_t + vec3d.field_72450_a * 4.0;
            entitylargefireball.field_70163_u = this.field_70163_u + (double)(this.field_70131_O / 2.0f) + 0.5;
            entitylargefireball.field_70161_v = this.field_70161_v + vec3d.field_72449_c * 4.0;
            this.field_70170_p.func_72838_d((Entity)entitylargefireball);
            for (int i = 0; i <= 2; ++i) {
                this.field_70170_p.func_175688_a(EnumParticleTypes.FLAME, this.field_70165_t + vec3d.field_72450_a * 4.0, this.field_70163_u + (double)(this.field_70131_O / 2.0f) + 0.5, this.field_70161_v + vec3d.field_72449_c * 4.0, 0.0, -1.0, 0.0, new int[0]);
            }
            return;
        }
        this.vomit = 40;
        if (this.field_70146_Z.nextBoolean()) {
            this.raining = true;
            this.rainingOrbs = 19;
            this.field_70170_p.func_72960_a((Entity)this, (byte)100);
            this.func_184185_a(SRPSounds.HEBLU_SHOOT, this.func_70599_aP() * 2.0f, (this.field_70146_Z.nextFloat() - this.field_70146_Z.nextFloat()) * 0.2f + 1.0f);
        } else {
            this.field_70170_p.func_72960_a((Entity)this, (byte)101);
        }
        if (!this.raining) {
            Vec3d vec3d = this.func_70676_i(1.0f);
            double bon = 12.5;
            float rad = 2.0f;
            for (int i = 0; i < 3; ++i) {
                EntityToxicCloud entityareaeffectcloud = new EntityToxicCloud(this.field_70170_p, this.field_70165_t + vec3d.field_72450_a * bon, Math.max(this.field_70163_u, target.field_70163_u), this.field_70161_v + vec3d.field_72449_c * bon);
                entityareaeffectcloud.setRadius(rad + 1.0f, 0.9f);
                entityareaeffectcloud.setDuration(100);
                entityareaeffectcloud.setRadiusPerTick(-entityareaeffectcloud.getRadius() / (float)entityareaeffectcloud.getDuration());
                entityareaeffectcloud.setOwner(this);
                this.field_70170_p.func_72960_a((Entity)entityareaeffectcloud, (byte)77);
                entityareaeffectcloud.addEffect(new PotionEffect(SRPPotions.COTH_E, 300, 0, false, true));
                this.field_70170_p.func_72838_d((Entity)entityareaeffectcloud);
                if (i == 1) {
                    bon += 4.0;
                }
                bon += 7.5 + (double)i;
                rad += 2.0f;
            }
            this.vomitPos = new BlockPos(this.field_70165_t + vec3d.field_72450_a * bon, this.field_70163_u, this.field_70161_v + vec3d.field_72449_c * bon);
        }
        this.setWait(80);
    }

    public void func_184724_a(boolean swingingArms) {
    }

    public float getaaa() {
        return this.aaa;
    }

    @Override
    public boolean func_70097_a(@Nonnull DamageSource source, float amount) {
        boolean flag = super.func_70097_a(source, amount);
        if (flag && this.field_70146_Z.nextInt(12) == 0 && !this.getFlyingState()) {
            this.changeStateTo(true);
        }
        return flag;
    }

    @Override
    public boolean attackEntityBodyFrom(DamageSource source, float amount, int id, boolean notify) {
        if (this.field_70170_p.field_72995_K) {
            return false;
        }
        boolean flag = this.func_70097_a(source, amount);
        if (!flag) {
            return false;
        }
        return flag;
    }

    @Override
    public void setBodyPartDead(int id) {
        if (this.leftTendril.getId() == id) {
            this.field_70170_p.func_72973_f((Entity)this.leftTendril);
        } else if (this.rightTendril.getId() == id) {
            this.field_70170_p.func_72973_f((Entity)this.rightTendril);
        } else if (this.head.getId() == id) {
            this.field_70170_p.func_72973_f((Entity)this.head);
        }
    }

    @Override
    public void func_70106_y() {
        if (this.head != null) {
            this.field_70170_p.func_72973_f((Entity)this.head);
        }
        if (this.leftTendril != null) {
            this.field_70170_p.func_72973_f((Entity)this.leftTendril);
        }
        if (this.rightTendril != null) {
            this.field_70170_p.func_72973_f((Entity)this.rightTendril);
        }
        super.func_70106_y();
    }

    @Override
    protected void spawnCloneCosmical(EntityPCosmical entityout) {
        entityout.func_70012_b(this.field_70165_t, this.field_70163_u, this.field_70161_v, this.field_70177_z, this.field_70125_A);
        entityout.func_180482_a(this.field_70170_p.func_175649_E(new BlockPos((Entity)entityout)), null);
        if (this.func_145818_k_()) {
            entityout.func_96094_a("--" + this.func_95999_t() + "--");
            entityout.func_174805_g(this.func_174833_aM());
        }
        this.field_70170_p.func_72838_d((Entity)entityout);
        entityout.particleStatus((byte)7);
        this.limitClones = entityout.func_145782_y();
        entityout.limitClones = this.func_145782_y();
        this.setShadowStatus(false);
        entityout.setCloneC();
        entityout.func_110148_a(SharedMonsterAttributes.field_111263_d).func_111128_a(entityout.func_110148_a(SharedMonsterAttributes.field_111263_d).func_111125_b() * 1.33);
        entityout.func_110148_a(SharedMonsterAttributes.field_111264_e).func_111128_a(entityout.func_110148_a(SharedMonsterAttributes.field_111264_e).func_111125_b() * 0.5);
        if (this.getFlyingState()) {
            ((EntityHeblu)entityout).changeStateTo(true);
        }
    }

    public void changeStateTo(boolean fly) {
        if (this.limit >= 1) {
            return;
        }
        if (fly) {
            if (!this.getFlyingState()) {
                if (this.leftTendrilHealth <= 0.0f || this.rightTendrilHealth <= 0.0f) {
                    return;
                }
                this.field_70765_h = new AIMoveControl(this);
                this.setParasiteStatus(3);
                this.field_70180_af.func_187227_b(FLYING, (Object)true);
                this.field_70181_x = 0.5;
                this.aaa += 0.08f;
                this.flying = 1;
                this.sss = 19.85f;
            }
        } else if (this.getFlyingState()) {
            this.field_70765_h = new EntityMoveHelper((EntityLiving)this);
            this.setParasiteStatus(0);
            this.field_70180_af.func_187227_b(FLYING, (Object)false);
            this.flying = 0;
            this.aaa = 0.0f;
            this.sss = 0.0f;
        }
    }

    public float func_70047_e() {
        return 1.75f;
    }

    @Override
    public boolean func_70652_k(@Nonnull Entity entityIn) {
        return super.func_70652_k(entityIn);
    }

    @Override
    public boolean attackEntityAsMobAOE(Entity entityIn) {
        return this.func_70652_k(entityIn);
    }

    @Override
    protected void selfExplode() {
    }

    @Override
    protected void spawnGore() {
    }

    protected SoundEvent func_184639_G() {
        if (this.getParasiteStatus() != 0) {
            return SRPSounds.MOBSILENCE;
        }
        return SRPSounds.HEBLU_GROWL;
    }

    protected SoundEvent func_184601_bQ(DamageSource damageSourceIn) {
        return SRPSounds.HEBLU_HURT;
    }

    protected float func_70599_aP() {
        return 5.0f;
    }

    protected SoundEvent func_184615_bR() {
        return SRPSounds.HEBLU_DEATH;
    }

    protected SoundEvent getStepSound() {
        return SRPSounds.HEBLU_STEP;
    }

    protected void func_180429_a(BlockPos pos, Block blockIn) {
        this.func_184185_a(this.getStepSound(), 0.15f, 1.0f);
    }

    @Override
    public IEntityLivingData func_180482_a(DifficultyInstance difficulty, IEntityLivingData livingdata) {
        IEntityLivingData floo = super.func_180482_a(difficulty, livingdata);
        return floo;
    }

    public boolean getFlyingState() {
        return (Boolean)this.field_70180_af.func_187225_a(FLYING);
    }

    @Override
    public void func_70014_b(NBTTagCompound compound) {
        super.func_70014_b(compound);
        compound.func_74776_a("parasiteleftTendril", this.leftTendrilHealth);
        compound.func_74776_a("parasiterightTendril", this.rightTendrilHealth);
    }

    @Override
    public void func_70037_a(NBTTagCompound compound) {
        super.func_70037_a(compound);
        if (compound.func_150297_b("parasiteleftTendril", 99)) {
            this.leftTendrilHealth = compound.func_74760_g("parasiteleftTendril");
            if (this.leftTendrilHealth <= 0.0f) {
                this.field_70170_p.func_72960_a((Entity)this, (byte)11);
            }
        }
        if (compound.func_150297_b("parasiterightTendril", 99)) {
            this.rightTendrilHealth = compound.func_74760_g("parasiterightTendril");
            if (this.rightTendrilHealth <= 0.0f) {
                this.field_70170_p.func_72960_a((Entity)this, (byte)22);
            }
        }
    }

    @SideOnly(value=Side.CLIENT)
    public float getLeft() {
        return this.leftTendrilHealth;
    }

    @SideOnly(value=Side.CLIENT)
    public float getRight() {
        return this.rightTendrilHealth;
    }

    @SideOnly(value=Side.CLIENT)
    public float getHead() {
        return this.headlHealth;
    }

    @Override
    @SideOnly(value=Side.CLIENT)
    public void func_70103_a(byte id) {
        if (id == 11) {
            this.leftTendrilHealth = 0.0f;
        } else if (id == 22) {
            this.rightTendrilHealth = 0.0f;
        } else if (id == 33) {
            this.headlHealth = 0.0f;
        } else if (id == 100) {
            this.vomit = 40;
            this.raining = true;
        } else if (id == 101) {
            this.vomit = 40;
        } else {
            super.func_70103_a(id);
        }
    }

    @Override
    protected EntityPCosmical getThis() {
        return new EntityHeblu(this.field_70170_p);
    }

    public void func_70091_d(MoverType type, double x, double y, double z) {
        super.func_70091_d(type, x, y, z);
        this.func_145775_I();
    }

    @Override
    protected void func_70088_a() {
        super.func_70088_a();
        this.field_70180_af.func_187214_a(VEX_FLAGS, (Object)0);
        this.field_70180_af.func_187214_a(FLYING, (Object)true);
        this.field_70180_af.func_187214_a(ATTACKING, (Object)false);
    }

    private boolean getVexFlag(int mask) {
        byte i = (Byte)this.field_70180_af.func_187225_a(VEX_FLAGS);
        return (i & mask) != 0;
    }

    private void setVexFlag(int mask, boolean value) {
        int i = ((Byte)this.field_70180_af.func_187225_a(VEX_FLAGS)).byteValue();
        i = value ? (i |= mask) : (i &= ~mask);
        this.field_70180_af.func_187227_b(VEX_FLAGS, (Object)((byte)(i & 0xFF)));
    }

    @SideOnly(value=Side.CLIENT)
    public boolean isAttacking() {
        return (Boolean)this.field_70180_af.func_187225_a(ATTACKING);
    }

    public void setAttacking(boolean attacking) {
        this.field_70180_af.func_187227_b(ATTACKING, (Object)attacking);
    }

    @Override
    public boolean getFinished(byte attID) {
        switch (attID) {
            case 1: {
                return this.skillFlame;
            }
        }
        return super.getFinished(attID);
    }

    @Override
    public void setFinished(byte attID, boolean in) {
        switch (attID) {
            case 1: {
                this.skillFlame = in;
                return;
            }
        }
        super.setFinished(attID, in);
    }

    @Override
    public void doSpecialSkill(byte id) {
        switch (id) {
            case 1: {
                this.flame();
                return;
            }
        }
        super.doSpecialSkill(id);
    }

    private void flame() {
        if (this.getFlyingState() || this.headlHealth <= 0.0f) {
            this.skillFlame = true;
            this.limit = 0;
            return;
        }
        if (this.limit == 0) {
            EntityLivingBase entitylivingbase = this.func_70638_az();
            if (entitylivingbase == null) {
                this.skillFlame = true;
                this.limit = 0;
                return;
            }
            this.tttX = entitylivingbase.field_70165_t;
            this.tttY = entitylivingbase.field_70163_u;
            this.tttZ = entitylivingbase.field_70161_v;
            this.tttH = entitylivingbase.func_174813_aQ().field_72338_b;
            this.tttHH = entitylivingbase.field_70131_O;
        }
        ++this.limit;
        this.setParasiteStatus(10);
        this.func_70661_as().func_75492_a(this.tttX, this.tttY, this.tttZ, 0.0);
        this.resetIdleTime();
        if (this.field_70173_aa % 10 != 0) {
            return;
        }
        double d1 = 4.0;
        Vec3d vec3d = this.func_70676_i(1.0f);
        double d2 = this.tttX - (this.field_70165_t + vec3d.field_72450_a * 4.0);
        double d3 = this.tttH + this.tttHH / 4.0 - (0.5 + this.field_70163_u + (double)(this.field_70131_O / 4.0f));
        double d4 = this.tttZ - (this.field_70161_v + vec3d.field_72449_c * 4.0);
        this.field_70170_p.func_180498_a((EntityPlayer)null, 1016, new BlockPos((Entity)this), 0);
        EntityProjectileAlafhaBall entitylargefireball = new EntityProjectileAlafhaBall(this.field_70170_p, (EntityLivingBase)this, d2, d3, d4);
        entitylargefireball.field_70165_t = this.field_70165_t + vec3d.field_72450_a * 4.0;
        entitylargefireball.field_70163_u = this.field_70163_u + (double)(this.field_70131_O / 2.0f) + 0.5;
        entitylargefireball.field_70161_v = this.field_70161_v + vec3d.field_72449_c * 4.0;
        this.field_70170_p.func_72838_d((Entity)entitylargefireball);
        if (this.limit >= 60) {
            this.skillFlame = true;
            this.setParasiteStatus(0);
            this.limit = 0;
        }
    }

    static class AIFireballAttack
    extends EntityAIBase {
        private final EntityHeblu parentEntity;
        public int attackTimer;

        public AIFireballAttack(EntityHeblu ghast) {
            this.parentEntity = ghast;
        }

        public boolean func_75250_a() {
            return this.parentEntity.func_70638_az() != null && this.parentEntity.getFlyingState() && this.parentEntity.headlHealth > 0.0f;
        }

        public void func_75249_e() {
            this.attackTimer = 0;
        }

        public void func_75251_c() {
            this.parentEntity.setAttacking(false);
        }

        public void func_75246_d() {
            EntityLivingBase entitylivingbase = this.parentEntity.func_70638_az();
            double d0 = 64.0;
            if (entitylivingbase == null) {
                return;
            }
            if (entitylivingbase.func_70068_e((Entity)this.parentEntity) < 4096.0 && this.parentEntity.func_70685_l((Entity)entitylivingbase)) {
                World world = this.parentEntity.field_70170_p;
                ++this.attackTimer;
                if (this.parentEntity.func_70644_a(SRPPotions.RAGE_E)) {
                    ++this.attackTimer;
                }
                this.parentEntity.resetIdleTime();
                if (this.attackTimer == 10) {
                    // empty if block
                }
                if (this.attackTimer == 20) {
                    if (this.parentEntity.field_70170_p.field_73012_v.nextInt(3) == 0 && entitylivingbase.field_70122_E) {
                        this.parentEntity.vomitPos = entitylivingbase.func_180425_c();
                        this.parentEntity.vomit = 40;
                        this.parentEntity.raining = true;
                        this.parentEntity.rainingOrbs = 19;
                        world.func_72960_a((Entity)this.parentEntity, (byte)100);
                        this.parentEntity.func_184185_a(SRPSounds.HEBLU_SHOOT, this.parentEntity.func_70599_aP() * 2.0f, (this.parentEntity.field_70170_p.field_73012_v.nextFloat() - this.parentEntity.field_70170_p.field_73012_v.nextFloat()) * 0.2f + 1.0f);
                        this.attackTimer = -60;
                        return;
                    }
                    double d1 = 4.0;
                    Vec3d vec3d = this.parentEntity.func_70676_i(1.0f);
                    double d2 = entitylivingbase.field_70165_t - (this.parentEntity.field_70165_t + vec3d.field_72450_a * 4.0);
                    double d3 = entitylivingbase.func_174813_aQ().field_72338_b + (double)(entitylivingbase.field_70131_O / 2.0f) - (0.5 + this.parentEntity.field_70163_u + (double)(this.parentEntity.field_70131_O / 2.0f));
                    double d4 = entitylivingbase.field_70161_v - (this.parentEntity.field_70161_v + vec3d.field_72449_c * 4.0);
                    world.func_180498_a((EntityPlayer)null, 1016, new BlockPos((Entity)this.parentEntity), 0);
                    EntityProjectileAlafhaBall entitylargefireball = new EntityProjectileAlafhaBall(world, (EntityLivingBase)this.parentEntity, d2, d3, d4);
                    entitylargefireball.field_70165_t = this.parentEntity.field_70165_t + vec3d.field_72450_a * 4.0;
                    entitylargefireball.field_70163_u = this.parentEntity.field_70163_u + (double)(this.parentEntity.field_70131_O / 2.0f) + 0.5;
                    entitylargefireball.field_70161_v = this.parentEntity.field_70161_v + vec3d.field_72449_c * 4.0;
                    world.func_72838_d((Entity)entitylargefireball);
                    this.parentEntity.field_70708_bq = 0;
                    this.attackTimer = -45;
                    for (int i = 0; i <= 2; ++i) {
                        this.parentEntity.field_70170_p.func_175688_a(EnumParticleTypes.FLAME, this.parentEntity.field_70165_t + vec3d.field_72450_a * 4.0, this.parentEntity.field_70163_u + (double)(this.parentEntity.field_70131_O / 2.0f) + 0.5, this.parentEntity.field_70161_v + vec3d.field_72449_c * 4.0, 0.0, -1.0, 0.0, new int[0]);
                    }
                }
            } else if (this.attackTimer > 0) {
                --this.attackTimer;
            }
            this.parentEntity.setAttacking(this.attackTimer > 10);
        }
    }

    class AIMoveRandom
    extends EntityAIBase {
        public AIMoveRandom() {
            this.func_75248_a(1);
        }

        public boolean func_75250_a() {
            return !EntityHeblu.this.func_70605_aq().func_75640_a() && EntityHeblu.this.field_70146_Z.nextInt(5) == 0 && EntityHeblu.this.getFlyingState();
        }

        public boolean func_75253_b() {
            return false;
        }

        public void func_75246_d() {
            BlockPos blockpos = new BlockPos((Entity)EntityHeblu.this);
            int flag = 1;
            double speed = 0.5;
            if (EntityHeblu.this.func_70638_az() != null) {
                if (EntityHeblu.this.func_70068_e((Entity)EntityHeblu.this.func_70638_az()) > 100.0) {
                    blockpos = new BlockPos((Entity)EntityHeblu.this.func_70638_az());
                    flag = 2;
                    speed += 0.25;
                } else if (EntityHeblu.this.func_70068_e((Entity)EntityHeblu.this.func_70638_az()) < 36.0) {
                    blockpos = new BlockPos((Entity)EntityHeblu.this.func_70638_az());
                    flag = 3;
                    speed += 0.25;
                }
            }
            for (int i = 0; i < 3; ++i) {
                BlockPos blockpos1 = blockpos.func_177982_a(EntityHeblu.this.field_70146_Z.nextInt(15) - 7, EntityHeblu.this.field_70146_Z.nextInt(11) - 5, EntityHeblu.this.field_70146_Z.nextInt(15) - 7);
                if (flag == 2) {
                    blockpos1 = blockpos.func_177982_a(EntityHeblu.this.field_70146_Z.nextInt(6) - 2, EntityHeblu.this.field_70146_Z.nextInt(7) - 2, EntityHeblu.this.field_70146_Z.nextInt(6) - 2);
                } else if (flag == 3) {
                    blockpos1 = blockpos.func_177982_a(EntityHeblu.this.field_70146_Z.nextInt(4) + 3, EntityHeblu.this.field_70146_Z.nextInt(5) + 4, EntityHeblu.this.field_70146_Z.nextInt(4) + 3);
                }
                if (!EntityHeblu.this.field_70170_p.func_175623_d(blockpos1)) continue;
                EntityHeblu.this.field_70765_h.func_75642_a((double)blockpos1.func_177958_n() + 0.5, (double)blockpos1.func_177956_o() + 0.5, (double)blockpos1.func_177952_p() + 0.5, speed);
                if (EntityHeblu.this.func_70638_az() != null) break;
                EntityHeblu.this.func_70671_ap().func_75650_a((double)blockpos1.func_177958_n() + 0.5, (double)blockpos1.func_177956_o() + 0.5, (double)blockpos1.func_177952_p() + 0.5, 180.0f, 20.0f);
                break;
            }
        }
    }

    class AIMoveControl
    extends EntityMoveHelper {
        public AIMoveControl(EntityHeblu vex) {
            super((EntityLiving)vex);
        }

        public void func_75641_c() {
            if (this.field_188491_h == EntityMoveHelper.Action.MOVE_TO) {
                double d0 = this.field_75646_b - EntityHeblu.this.field_70165_t;
                double d1 = this.field_75647_c - EntityHeblu.this.field_70163_u;
                double d2 = this.field_75644_d - EntityHeblu.this.field_70161_v;
                double d3 = d0 * d0 + d1 * d1 + d2 * d2;
                if ((d3 = (double)MathHelper.func_76133_a((double)d3)) < EntityHeblu.this.func_174813_aQ().func_72320_b()) {
                    this.field_188491_h = EntityMoveHelper.Action.WAIT;
                    EntityHeblu.this.field_70159_w *= 0.5;
                    EntityHeblu.this.field_70181_x *= 0.5;
                    EntityHeblu.this.field_70179_y *= 0.5;
                } else {
                    EntityHeblu.this.field_70159_w += d0 / d3 * 0.05 * this.field_75645_e;
                    EntityHeblu.this.field_70181_x += d1 / d3 * 0.05 * this.field_75645_e;
                    EntityHeblu.this.field_70179_y += d2 / d3 * 0.05 * this.field_75645_e;
                    if (EntityHeblu.this.func_70638_az() == null) {
                        EntityHeblu.this.field_70761_aq = EntityHeblu.this.field_70177_z = -((float)MathHelper.func_181159_b((double)EntityHeblu.this.field_70159_w, (double)EntityHeblu.this.field_70179_y)) * 57.295776f;
                    } else {
                        double d4 = EntityHeblu.this.func_70638_az().field_70165_t - EntityHeblu.this.field_70165_t;
                        double d5 = EntityHeblu.this.func_70638_az().field_70161_v - EntityHeblu.this.field_70161_v;
                        EntityHeblu.this.field_70761_aq = EntityHeblu.this.field_70177_z = -((float)MathHelper.func_181159_b((double)d4, (double)d5)) * 57.295776f;
                    }
                }
            }
        }
    }
}
