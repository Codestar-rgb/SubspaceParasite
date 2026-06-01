package com.srp.client.model;

import com.srp.entity.SpeCowEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class SpeCowModel extends GeoModel<SpeCowEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_speCow.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_speCow.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_speCow.animation.json");

    @Override
    public ResourceLocation getModelResource(SpeCowEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(SpeCowEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(SpeCowEntity animatable) {
        return ANIMATION;
    }
}
