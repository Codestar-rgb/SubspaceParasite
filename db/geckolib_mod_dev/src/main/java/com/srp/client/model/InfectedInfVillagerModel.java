package com.srp.client.model;

import com.srp.entity.InfectedInfVillagerEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfectedInfVillagerModel extends GeoModel<InfectedInfVillagerEntity> {

    // Multi-part entity — primary model: {'name': 'infVillager', 'has_animation': True}
    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_{'name': 'infVillager', 'has_animation': True}.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_{'name': 'infVillager', 'has_animation': True}.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_{'name': 'infVillager', 'has_animation': True}.animation.json");

    @Override
    public ResourceLocation getModelResource(InfectedInfVillagerEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfectedInfVillagerEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfectedInfVillagerEntity animatable) {
        return ANIMATION;
    }
}
