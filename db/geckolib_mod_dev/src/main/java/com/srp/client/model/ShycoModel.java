package com.srp.client.model;

import com.srp.entity.ShycoEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class ShycoModel extends GeoModel<ShycoEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/primitive_shyco.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/primitive_shyco.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/primitive_shyco.animation.json");

    @Override
    public ResourceLocation getModelResource(ShycoEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(ShycoEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(ShycoEntity animatable) {
        return ANIMATION;
    }
}
