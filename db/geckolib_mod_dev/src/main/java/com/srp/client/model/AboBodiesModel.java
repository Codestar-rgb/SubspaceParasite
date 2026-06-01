package com.srp.client.model;

import com.srp.entity.AboBodiesEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class AboBodiesModel extends GeoModel<AboBodiesEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/abomination_aboBodies.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/abomination_aboBodies.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/abomination_aboBodies.animation.json");

    @Override
    public ResourceLocation getModelResource(AboBodiesEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(AboBodiesEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(AboBodiesEntity animatable) {
        return ANIMATION;
    }
}
