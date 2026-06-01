package com.srp.client.model;

import com.srp.entity.DodTEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class DodTModel extends GeoModel<DodTEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_dodT.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_dodT.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_dodT.animation.json");

    @Override
    public ResourceLocation getModelResource(DodTEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(DodTEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(DodTEntity animatable) {
        return ANIMATION;
    }
}
