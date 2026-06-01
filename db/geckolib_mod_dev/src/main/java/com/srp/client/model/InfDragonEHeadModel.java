package com.srp.client.model;

import com.srp.entity.InfDragonEHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfDragonEHeadModel extends GeoModel<InfDragonEHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infDragonEHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infDragonEHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infDragonEHead.animation.json");

    @Override
    public ResourceLocation getModelResource(InfDragonEHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfDragonEHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfDragonEHeadEntity animatable) {
        return ANIMATION;
    }
}
