package com.srp.client.model;

import com.srp.entity.LeemSiiEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LeemSiiModel extends GeoModel<LeemSiiEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_leemSII.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_leemSII.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_leemSII.animation.json");

    @Override
    public ResourceLocation getModelResource(LeemSiiEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LeemSiiEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LeemSiiEntity animatable) {
        return ANIMATION;
    }
}
