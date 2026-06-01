package com.srp.client.model;

import com.srp.entity.InfPlayerEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfPlayerModel extends GeoModel<InfPlayerEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infPlayer.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infPlayer.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infPlayer.animation.json");

    @Override
    public ResourceLocation getModelResource(InfPlayerEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfPlayerEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfPlayerEntity animatable) {
        return ANIMATION;
    }
}
