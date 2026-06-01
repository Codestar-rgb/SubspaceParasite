package com.srp.client.model;

import com.srp.entity.VenkrolSivEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class VenkrolSivModel extends GeoModel<VenkrolSivEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_venkrolSIV.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_venkrolSIV.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_venkrolSIV.animation.json");

    @Override
    public ResourceLocation getModelResource(VenkrolSivEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(VenkrolSivEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(VenkrolSivEntity animatable) {
        return ANIMATION;
    }
}
