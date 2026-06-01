package com.srp.client.model;

import com.srp.entity.ShycoAdaptedEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class ShycoAdaptedModel extends GeoModel<ShycoAdaptedEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/adapted_shycoAdapted.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/adapted_shycoAdapted.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/adapted_shycoAdapted.animation.json");

    @Override
    public ResourceLocation getModelResource(ShycoAdaptedEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(ShycoAdaptedEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(ShycoAdaptedEntity animatable) {
        return ANIMATION;
    }
}
