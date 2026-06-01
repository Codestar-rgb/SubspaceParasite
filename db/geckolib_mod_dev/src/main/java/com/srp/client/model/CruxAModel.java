package com.srp.client.model;

import com.srp.entity.CruxAEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class CruxAModel extends GeoModel<CruxAEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_cruxA.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_cruxA.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_cruxA.animation.json");

    @Override
    public ResourceLocation getModelResource(CruxAEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(CruxAEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(CruxAEntity animatable) {
        return ANIMATION;
    }
}
