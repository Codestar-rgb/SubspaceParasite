package com.srp.client.model;

import com.srp.entity.IkiEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class IkiModel extends GeoModel<IkiEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_iki.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_iki.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/primitive_iki.animation.json");

    @Override
    public ResourceLocation getModelResource(IkiEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(IkiEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(IkiEntity animatable) {
        return ANIMATION;
    }
}
