package com.srp.client.model;

import com.srp.entity.InfSquidEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfSquidModel extends GeoModel<InfSquidEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infSquid.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infSquid.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infSquid.animation.json");

    @Override
    public ResourceLocation getModelResource(InfSquidEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfSquidEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfSquidEntity animatable) {
        return ANIMATION;
    }
}
