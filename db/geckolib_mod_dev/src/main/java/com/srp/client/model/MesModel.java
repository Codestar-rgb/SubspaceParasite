package com.srp.client.model;

import com.srp.entity.MesEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class MesModel extends GeoModel<MesEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_mes.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_mes.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_mes.animation.json");

    @Override
    public ResourceLocation getModelResource(MesEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(MesEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(MesEntity animatable) {
        return ANIMATION;
    }
}
