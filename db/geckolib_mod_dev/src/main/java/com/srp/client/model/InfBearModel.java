package com.srp.client.model;

import com.srp.entity.InfBearEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfBearModel extends GeoModel<InfBearEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infBear.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infBear.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infBear.animation.json");

    @Override
    public ResourceLocation getModelResource(InfBearEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfBearEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfBearEntity animatable) {
        return ANIMATION;
    }
}
