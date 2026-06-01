package com.srp.client.model;

import com.srp.entity.VenkrolEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class VenkrolModel extends GeoModel<VenkrolEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_venkrol.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_venkrol.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_venkrol.animation.json");

    @Override
    public ResourceLocation getModelResource(VenkrolEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(VenkrolEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(VenkrolEntity animatable) {
        return ANIMATION;
    }
}
