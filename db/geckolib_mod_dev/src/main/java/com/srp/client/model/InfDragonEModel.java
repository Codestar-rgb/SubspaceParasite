package com.srp.client.model;

import com.srp.entity.InfDragonEEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfDragonEModel extends GeoModel<InfDragonEEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infDragonE.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infDragonE.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infDragonE.animation.json");

    @Override
    public ResourceLocation getModelResource(InfDragonEEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfDragonEEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfDragonEEntity animatable) {
        return ANIMATION;
    }
}
