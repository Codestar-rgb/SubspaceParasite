package com.srp.client.model;

import com.srp.entity.VestaEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class VestaModel extends GeoModel<VestaEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_vesta.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_vesta.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_vesta.animation.json");

    @Override
    public ResourceLocation getModelResource(VestaEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(VestaEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(VestaEntity animatable) {
        return ANIMATION;
    }
}
