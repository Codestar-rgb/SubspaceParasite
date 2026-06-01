package com.srp.client.model;

import com.srp.entity.UnvoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class UnvoModel extends GeoModel<UnvoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_unvo.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_unvo.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_unvo.animation.json");

    @Override
    public ResourceLocation getModelResource(UnvoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(UnvoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(UnvoEntity animatable) {
        return ANIMATION;
    }
}
