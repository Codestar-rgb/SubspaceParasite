package com.srp.client.model;

import com.srp.entity.TendrilBanoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TendrilBanoModel extends GeoModel<TendrilBanoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_tendrilBano.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_tendrilBano.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/misc_tendrilBano.animation.json");

    @Override
    public ResourceLocation getModelResource(TendrilBanoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TendrilBanoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TendrilBanoEntity animatable) {
        return ANIMATION;
    }
}
