/*
 * Decompiled with CFR 0.152.
 * 
 * Could not load the following classes:
 *  net.minecraft.client.renderer.entity.RenderManager
 *  net.minecraft.util.ResourceLocation
 */
package com.dhanantry.scapeandrunparasites.client.renderer.entity.derived;

import com.dhanantry.scapeandrunparasites.client.model.entity.derived.ModelKirin;
import com.dhanantry.scapeandrunparasites.client.renderer.RenderCosmical;
import com.dhanantry.scapeandrunparasites.entity.monster.derived.EntityKirin;
import net.minecraft.client.renderer.entity.RenderManager;
import net.minecraft.util.ResourceLocation;

public class RenderKirin
extends RenderCosmical<EntityKirin> {
    public static final ResourceLocation TEXTURES = new ResourceLocation("srparasites:textures/entity/monster/kirin.png");
    public static final ResourceLocation TEXTURESEC = new ResourceLocation("srparasites:textures/entity/monster/testb.png");

    public RenderKirin(RenderManager manager) {
        super(manager, new ModelKirin(), 1.3f);
    }

    protected ResourceLocation getEntityTexture(EntityKirin entity) {
        return TEXTURES;
    }

    @Override
    protected ResourceLocation getEntityTextureCosmical(EntityKirin entity) {
        return TEXTURESEC;
    }
}
