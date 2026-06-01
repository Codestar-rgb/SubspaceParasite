package com.srp.client.model;

import com.srp.entity.TonroEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TonroModel extends GeoModel<TonroEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/deterrent_tonro.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/deterrent_tonro.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/deterrent_tonro.animation.json");

    @Override
    public ResourceLocation getModelResource(TonroEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TonroEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TonroEntity animatable) {
        return ANIMATION;
    }
}
