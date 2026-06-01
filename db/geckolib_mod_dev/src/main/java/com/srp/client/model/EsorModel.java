package com.srp.client.model;

import com.srp.entity.EsorEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class EsorModel extends GeoModel<EsorEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/pure_esor.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/pure_esor.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/pure_esor.animation.json");

    @Override
    public ResourceLocation getModelResource(EsorEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(EsorEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(EsorEntity animatable) {
        return ANIMATION;
    }
}
