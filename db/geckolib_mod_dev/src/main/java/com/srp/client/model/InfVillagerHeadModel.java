package com.srp.client.model;

import com.srp.entity.InfVillagerHeadEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InfVillagerHeadModel extends GeoModel<InfVillagerHeadEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/infected_infVillagerHead.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/infected_infVillagerHead.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/infected_infVillagerHead.animation.json");

    @Override
    public ResourceLocation getModelResource(InfVillagerHeadEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InfVillagerHeadEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InfVillagerHeadEntity animatable) {
        return ANIMATION;
    }
}
