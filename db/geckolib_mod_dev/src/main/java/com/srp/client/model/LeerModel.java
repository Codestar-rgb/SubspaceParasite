package com.srp.client.model;

import com.srp.entity.LeerEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class LeerModel extends GeoModel<LeerEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_leer.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_leer.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_leer.animation.json");

    @Override
    public ResourceLocation getModelResource(LeerEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(LeerEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(LeerEntity animatable) {
        return ANIMATION;
    }
}
