package com.srp.client.model;

import com.srp.entity.TendrilNoglaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class TendrilNoglaModel extends GeoModel<TendrilNoglaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_tendrilNogla.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_tendrilNogla.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/misc_tendrilNogla.animation.json");

    @Override
    public ResourceLocation getModelResource(TendrilNoglaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(TendrilNoglaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(TendrilNoglaEntity animatable) {
        return ANIMATION;
    }
}
