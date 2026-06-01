package com.srp.client.model;

import com.srp.entity.SpeBearEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class SpeBearModel extends GeoModel<SpeBearEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_speBear.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_speBear.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_speBear.animation.json");

    @Override
    public ResourceLocation getModelResource(SpeBearEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(SpeBearEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(SpeBearEntity animatable) {
        return ANIMATION;
    }
}
