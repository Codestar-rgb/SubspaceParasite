package com.srp.client.model;

import com.srp.entity.RatholEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class RatholModel extends GeoModel<RatholEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/inborn_rathol.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/inborn_rathol.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/inborn_rathol.animation.json");

    @Override
    public ResourceLocation getModelResource(RatholEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(RatholEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(RatholEntity animatable) {
        return ANIMATION;
    }
}
