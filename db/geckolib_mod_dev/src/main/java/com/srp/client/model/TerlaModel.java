package com.srp.client.model;

import com.srp.entity.TerlaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TerlaModel extends GeoModel<TerlaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/ancient_terla.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/ancient_terla.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/ancient_terla.animation.json");

    @Override
    public ResourceLocation getModelResource(TerlaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TerlaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TerlaEntity animatable) {
        return ANIMATION;
    }
}
