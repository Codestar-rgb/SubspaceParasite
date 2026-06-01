package com.srp.client.model;

import com.srp.entity.AboHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class AboHeadModel extends GeoModel<AboHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/abomination_aboHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/abomination_aboHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/abomination_aboHead.animation.json");

    @Override
    public ResourceLocation getModelResource(AboHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(AboHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(AboHeadEntity animatable) {
        return ANIMATION;
    }
}
