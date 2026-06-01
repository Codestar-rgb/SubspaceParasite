package com.srp.client.model;

import com.srp.entity.SpeSheepEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class SpeSheepModel extends GeoModel<SpeSheepEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_speSheep.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_speSheep.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_speSheep.animation.json");

    @Override
    public ResourceLocation getModelResource(SpeSheepEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(SpeSheepEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(SpeSheepEntity animatable) {
        return ANIMATION;
    }
}
