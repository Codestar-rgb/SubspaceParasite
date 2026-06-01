package com.srp.client.model;

import com.srp.entity.DodSiiEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DodSiiModel extends GeoModel<DodSiiEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_dodSII.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_dodSII.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_dodSII.animation.json");

    @Override
    public ResourceLocation getModelResource(DodSiiEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DodSiiEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DodSiiEntity animatable) {
        return ANIMATION;
    }
}
