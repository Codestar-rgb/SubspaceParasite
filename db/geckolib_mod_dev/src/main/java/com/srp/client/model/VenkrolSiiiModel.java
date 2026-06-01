package com.srp.client.model;

import com.srp.entity.VenkrolSiiiEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class VenkrolSiiiModel extends GeoModel<VenkrolSiiiEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_venkrolSIII.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_venkrolSIII.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_venkrolSIII.animation.json");

    @Override
    public ResourceLocation getModelResource(VenkrolSiiiEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(VenkrolSiiiEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(VenkrolSiiiEntity animatable) {
        return ANIMATION;
    }
}
