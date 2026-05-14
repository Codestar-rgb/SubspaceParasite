/*
 * Decompiled with CFR 0.152.
 * 
 * Could not load the following classes:
 *  javax.annotation.Nonnull
 *  net.minecraft.entity.Entity
 *  net.minecraft.entity.EntityCreature
 *  net.minecraft.entity.EntityLiving
 *  net.minecraft.entity.EntityLivingBase
 *  net.minecraft.entity.SharedMonsterAttributes
 *  net.minecraft.entity.ai.EntityAIBase
 *  net.minecraft.entity.ai.EntityAIHurtByTarget
 *  net.minecraft.nbt.NBTTagCompound
 *  net.minecraft.network.datasync.DataParameter
 *  net.minecraft.network.datasync.DataSerializer
 *  net.minecraft.network.datasync.DataSerializers
 *  net.minecraft.network.datasync.EntityDataManager
 *  net.minecraft.util.DamageSource
 *  net.minecraft.util.EnumParticleTypes
 *  net.minecraft.util.SoundEvent
 *  net.minecraft.util.math.BlockPos
 *  net.minecraft.world.World
 */
package com.dhanantry.scapeandrunparasites.entity.monster.derived;

import com.dhanantry.scapeandrunparasites.client.SRPClientParticles;
import com.dhanantry.scapeandrunparasites.entity.EntityOrbVoid;
import com.dhanantry.scapeandrunparasites.entity.ai.EntityAIAttackMeleeStatus;
import com.dhanantry.scapeandrunparasites.entity.ai.EntityAIKirinBlink;
import com.dhanantry.scapeandrunparasites.entity.ai.EntityAISkill;
import com.dhanantry.scapeandrunparasites.entity.ai.EntityAISwimmingDiving;
import com.dhanantry.scapeandrunparasites.entity.ai.misc.EntityPCosmical;
import com.dhanantry.scapeandrunparasites.entity.ai.misc.EntityPDerived;
import com.dhanantry.scapeandrunparasites.init.SRPSounds;
import com.dhanantry.scapeandrunparasites.util.SRPAttributes;
import com.dhanantry.scapeandrunparasites.util.config.SRPConfig;
import java.util.Objects;
import javax.annotation.Nonnull;
import net.minecraft.entity.Entity;
import net.minecraft.entity.EntityCreature;
import net.minecraft.entity.EntityLiving;
import net.minecraft.entity.EntityLivingBase;
import net.minecraft.entity.SharedMonsterAttributes;
import net.minecraft.entity.ai.EntityAIBase;
import net.minecraft.entity.ai.EntityAIHurtByTarget;
import net.minecraft.nbt.NBTTagCompound;
import net.minecraft.network.datasync.DataParameter;
import net.minecraft.network.datasync.DataSerializer;
import net.minecraft.network.datasync.DataSerializers;
import net.minecraft.network.datasync.EntityDataManager;
import net.minecraft.util.DamageSource;
import net.minecraft.util.EnumParticleTypes;
import net.minecraft.util.SoundEvent;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;

public class EntityKirin
extends EntityPDerived {
    private int voidCool;
    private int voidCoolTotal;
    private int floatBob;
    private static final int FLOAT_GROUND_SCAN = 24;
    private static final double FLOAT_HOVER_HEIGHT = 0.35;
    private static final double FLOAT_BOB_AMPLITUDE = 0.06;
    private int noGroundTicks = 0;
    private static final double FLOAT_UP_MAX = 0.16;
    private static final double FLOAT_DOWN_MAX = -0.16;
    private static final DataParameter<BlockPos> BLINK_POS = EntityDataManager.func_187226_a(EntityKirin.class, (DataSerializer)DataSerializers.field_187200_j);
    private static final DataParameter<Integer> BLINK_TICKS = EntityDataManager.func_187226_a(EntityKirin.class, (DataSerializer)DataSerializers.field_187192_b);
    private int limit;
    private int border;
    private boolean skillSummon;

    public EntityKirin(World worldIn) {
        super(worldIn);
        this.func_70105_a(2.1271334f, 7.1f);
        this.field_70138_W = 1.0f;
        this.field_70714_bg.func_85156_a((EntityAIBase)this.folow);
        this.voidCool = this.voidCoolTotal = 5;
    }

    @Override
    protected void func_70088_a() {
        super.func_70088_a();
        this.field_70180_af.func_187214_a(BLINK_POS, (Object)BlockPos.field_177992_a);
        this.field_70180_af.func_187214_a(BLINK_TICKS, (Object)0);
    }

    public void setBlinkCharge(BlockPos pos, int ticks) {
        if (pos == null) {
            pos = BlockPos.field_177992_a;
        }
        this.field_70180_af.func_187227_b(BLINK_POS, (Object)pos);
        this.field_70180_af.func_187227_b(BLINK_TICKS, (Object)Math.max(0, ticks));
    }

    public void clearBlinkCharge() {
        this.field_70180_af.func_187227_b(BLINK_POS, (Object)BlockPos.field_177992_a);
        this.field_70180_af.func_187227_b(BLINK_TICKS, (Object)0);
    }

    protected SoundEvent func_184639_G() {
        if (this.getParasiteStatus() != 0) {
            return SRPSounds.MOBSILENCE;
        }
        return SRPSounds.KIRIN_GROWL;
    }

    protected SoundEvent func_184601_bQ(DamageSource damageSourceIn) {
        if (this.field_70146_Z.nextBoolean() && this.getHitStatus() > 0) {
            return SRPSounds.MOBSILENCE;
        }
        return SRPSounds.KIRIN_HURT;
    }

    protected SoundEvent func_184615_bR() {
        return SRPSounds.KIRIN_DEATH;
    }

    public void func_70071_h_() {
        BlockPos p;
        int ticks;
        super.func_70071_h_();
        if (this.field_70170_p.field_72995_K && (ticks = ((Integer)this.field_70180_af.func_187225_a(BLINK_TICKS)).intValue()) > 0 && (p = (BlockPos)this.field_70180_af.func_187225_a(BLINK_POS)) != null && !Objects.equals(p, BlockPos.field_177992_a)) {
            float t = 1.0f - (float)ticks / 60.0f;
            double y = (double)p.func_177956_o() + 1.5 + (double)t;
            double cx = (double)p.func_177958_n() + 0.5;
            double cz = (double)p.func_177952_p() + 0.5;
            float sizeBig = 6.0f;
            float sizeSmall = 5.5f;
            double base = 0.35;
            double accel = 1.25;
            double spd = base + (double)t * accel;
            float angSmall = (float)((double)this.field_70173_aa * spd % (Math.PI * 2));
            float angBig = (float)((double)this.field_70173_aa * -spd % (Math.PI * 2));
            SRPClientParticles.spawnKirinWarning(this.field_70170_p, cx, y, cz, sizeSmall, angSmall, 1);
            SRPClientParticles.spawnKirinWarning(this.field_70170_p, cx, y, cz, sizeBig, angBig, 1);
        }
    }

    @Override
    public int getParasiteIDRegister() {
        return 67;
    }

    protected void func_184651_r() {
        this.field_70715_bh.func_75776_a(1, (EntityAIBase)new EntityAIHurtByTarget((EntityCreature)this, true, new Class[0]));
        this.field_70714_bg.func_75776_a(0, (EntityAIBase)new EntityAISwimmingDiving((EntityLiving)this, 0.08));
        this.field_70714_bg.func_75776_a(2, (EntityAIBase)new EntityAIKirinBlink(this));
        this.field_70714_bg.func_75776_a(3, (EntityAIBase)new EntityAIAttackMeleeStatus(this, 1.0, true, 0.0));
        this.field_70714_bg.func_75776_a(2, (EntityAIBase)new EntityAISkill(this, 80, 35, true, 1));
    }

    protected void func_110147_ax() {
        super.func_110147_ax();
        this.func_110148_a(SharedMonsterAttributes.field_111267_a).func_111128_a(SRPAttributes.KIRIN_HEALTH);
        this.func_110148_a(SharedMonsterAttributes.field_188791_g).func_111128_a(SRPAttributes.KIRIN_ARMOR);
        this.func_110148_a(SharedMonsterAttributes.field_111263_d).func_111128_a(0.24);
        this.func_110148_a(SharedMonsterAttributes.field_111266_c).func_111128_a(SRPAttributes.KIRIN_KD_RESISTANCE);
        this.func_110148_a(SharedMonsterAttributes.field_111264_e).func_111128_a(SRPAttributes.KIRIN_ATTACK_DAMAGE);
        this.func_110148_a(SharedMonsterAttributes.field_111265_b).func_111128_a(SRPConfig.derivedFollow);
    }

    @Override
    public void func_70636_d() {
        super.func_70636_d();
        if (!this.field_70170_p.field_72995_K) {
            this.updateFloating();
        }
        if (this.field_70170_p.field_72995_K) {
            for (int i = 0; i < 4; ++i) {
                this.field_70170_p.func_175688_a(EnumParticleTypes.PORTAL, this.field_70165_t + (this.field_70146_Z.nextDouble() - 0.5) * ((double)this.field_70130_N * 3.0), this.field_70163_u + this.field_70146_Z.nextDouble() * (double)this.field_70131_O - 0.25, this.field_70161_v + (this.field_70146_Z.nextDouble() - 0.5) * ((double)this.field_70130_N * 3.0), (this.field_70146_Z.nextDouble() - 0.5) * 2.0, -this.field_70146_Z.nextDouble(), (this.field_70146_Z.nextDouble() - 0.5) * 2.0, new int[0]);
            }
        }
    }

    @Override
    public boolean func_70097_a(@Nonnull DamageSource source, float amount) {
        boolean flag = super.func_70097_a(source, amount);
        if (flag) {
            // empty if block
        }
        return flag;
    }

    @Override
    public boolean func_70652_k(@Nonnull Entity entityIn) {
        boolean flag = super.func_70652_k(entityIn);
        if (flag) {
            // empty if block
        }
        return flag;
    }

    public float func_70047_e() {
        return 5.7f;
    }

    @Override
    public boolean scaryOrbEffect(EntityLivingBase in, int mobs) {
        boolean flag = super.scaryOrbEffect(in, mobs);
        if (flag) {
            // empty if block
        }
        return flag;
    }

    @Override
    public void func_70014_b(NBTTagCompound compound) {
        super.func_70014_b(compound);
    }

    protected float func_70599_aP() {
        return 5.0f;
    }

    @Override
    public void func_70037_a(NBTTagCompound compound) {
        super.func_70037_a(compound);
    }

    @Override
    protected EntityPCosmical getThis() {
        return new EntityKirin(this.field_70170_p);
    }

    @Override
    public boolean getFinished(byte attID) {
        switch (attID) {
            case 1: {
                return this.skillSummon;
            }
        }
        return super.getFinished(attID);
    }

    @Override
    public void setFinished(byte attID, boolean in) {
        switch (attID) {
            case 1: {
                this.skillSummon = in;
                return;
            }
        }
        super.setFinished(attID, in);
    }

    @Override
    public void doSpecialSkill(byte id) {
        switch (id) {
            case 1: {
                this.summon();
                return;
            }
        }
        super.doSpecialSkill(id);
    }

    private void summon() {
        this.field_70181_x = 0.0;
        this.field_70163_u = this.field_70167_r;
        this.setParasiteStatus(30);
        this.func_70661_as().func_75499_g();
        if (this.field_70173_aa % 20 != 0) {
            return;
        }
        ++this.border;
        this.field_70170_p.func_72960_a((Entity)this, (byte)100);
        if (this.getCloneC() || this.func_70638_az() == null) {
            this.skillSummon = true;
            this.setParasiteStatus(0);
            this.border = 0;
            this.limit = 0;
        } else if (!this.func_70638_az().func_70089_S()) {
            ++this.border;
        }
        if (this.border == 3) {
            EntityOrbVoid orb = new EntityOrbVoid(this.field_70170_p, this, 8, 80, true);
            orb.func_82149_j((Entity)this);
            double off = 10.0;
            orb.field_70163_u += (double)this.field_70131_O + off;
            orb.offsetOrb = off;
            this.field_70170_p.func_72838_d((Entity)orb);
            this.func_184185_a(SRPSounds.KIRIN_SHOOT, this.func_70599_aP() * 2.0f, (this.field_70146_Z.nextFloat() - this.field_70146_Z.nextFloat()) * 0.2f + 1.0f);
        }
        if (this.border > 12) {
            this.skillSummon = true;
            this.setParasiteStatus(0);
            this.border = 0;
            this.limit = 0;
        }
    }

    private void updateFloating() {
        this.field_70143_R = 0.0f;
        ++this.floatBob;
        double bob = Math.sin((double)(this.field_70173_aa + this.floatBob) * 0.12) * 0.06;
        BlockPos base = new BlockPos(this.field_70165_t, this.field_70163_u + 0.1, this.field_70161_v);
        BlockPos ground = null;
        for (int i = 0; i <= 24; ++i) {
            BlockPos p = base.func_177979_c(i);
            if (!this.field_70170_p.func_180495_p(p).func_185917_h()) continue;
            ground = p;
            break;
        }
        if (ground == null) {
            this.field_70181_x = 0.0;
            ++this.noGroundTicks;
            if (!this.field_70170_p.field_72995_K && this.noGroundTicks >= 40 && EntityAIKirinBlink.tryBlinkToNearbyLand(this, 48, 20)) {
                this.noGroundTicks = 0;
            }
            return;
        }
        this.noGroundTicks = 0;
        double targetY = (double)ground.func_177956_o() + 1.0 + 0.35 + bob;
        double dy = targetY - this.field_70163_u;
        double accel = dy > 0.0 ? dy * 0.12 : dy * 0.06;
        this.field_70181_x += accel;
        if (this.field_70181_x > 0.16) {
            this.field_70181_x = 0.16;
        }
        if (this.field_70181_x < -0.16) {
            this.field_70181_x = -0.16;
        }
    }
}
