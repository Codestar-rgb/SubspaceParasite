package com.srp.client.model;

import com.srp.entity.NakEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class NakModel extends GeoModel<NakEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_nak.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_nak.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_nak.animation.json");

    @Override
    public ResourceLocation getModelResource(NakEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(NakEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(NakEntity animatable) {
        return ANIMATION;
    }
}
