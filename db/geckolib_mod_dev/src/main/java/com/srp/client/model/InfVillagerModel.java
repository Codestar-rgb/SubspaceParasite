package com.srp.client.model;

import com.srp.entity.InfVillagerEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfVillagerModel extends GeoModel<InfVillagerEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infVillager.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infVillager.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infVillager.animation.json");

    @Override
    public ResourceLocation getModelResource(InfVillagerEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfVillagerEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfVillagerEntity animatable) {
        return ANIMATION;
    }
}
