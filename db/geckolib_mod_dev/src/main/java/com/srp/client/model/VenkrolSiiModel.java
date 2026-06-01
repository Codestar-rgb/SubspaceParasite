package com.srp.client.model;

import com.srp.entity.VenkrolSiiEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class VenkrolSiiModel extends GeoModel<VenkrolSiiEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_venkrolSII.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_venkrolSII.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_venkrolSII.animation.json");

    @Override
    public ResourceLocation getModelResource(VenkrolSiiEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(VenkrolSiiEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(VenkrolSiiEntity animatable) {
        return ANIMATION;
    }
}
