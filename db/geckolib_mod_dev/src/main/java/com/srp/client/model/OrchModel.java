package com.srp.client.model;

import com.srp.entity.OrchEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class OrchModel extends GeoModel<OrchEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_orch.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_orch.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_orch.animation.json");

    @Override
    public ResourceLocation getModelResource(OrchEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(OrchEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(OrchEntity animatable) {
        return ANIMATION;
    }
}
