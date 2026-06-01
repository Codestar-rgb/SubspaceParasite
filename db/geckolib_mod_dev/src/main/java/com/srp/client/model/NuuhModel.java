package com.srp.client.model;

import com.srp.entity.NuuhEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class NuuhModel extends GeoModel<NuuhEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_nuuh.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_nuuh.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/inborn_nuuh.animation.json");

    @Override
    public ResourceLocation getModelResource(NuuhEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(NuuhEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(NuuhEntity animatable) {
        return ANIMATION;
    }
}
