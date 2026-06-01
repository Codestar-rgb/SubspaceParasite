package com.srp.client.model;

import com.srp.entity.CruxBEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class CruxBModel extends GeoModel<CruxBEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_cruxB.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_cruxB.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_cruxB.animation.json");

    @Override
    public ResourceLocation getModelResource(CruxBEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(CruxBEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(CruxBEntity animatable) {
        return ANIMATION;
    }
}
