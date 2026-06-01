package com.srp.client.model;

import com.srp.entity.InfCowEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfCowModel extends GeoModel<InfCowEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infCow.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infCow.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infCow.animation.json");

    @Override
    public ResourceLocation getModelResource(InfCowEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfCowEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfCowEntity animatable) {
        return ANIMATION;
    }
}
