package com.srp.client.model;

import com.srp.entity.SpeVillagerEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class SpeVillagerModel extends GeoModel<SpeVillagerEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_speVillager.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_speVillager.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_speVillager.animation.json");

    @Override
    public ResourceLocation getModelResource(SpeVillagerEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(SpeVillagerEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(SpeVillagerEntity animatable) {
        return ANIMATION;
    }
}
