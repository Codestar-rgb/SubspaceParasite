package com.srp.client.model;

import com.srp.entity.ProjectileHommingEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class ProjectileHommingModel extends GeoModel<ProjectileHommingEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/misc_projectileHomming.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/misc_projectileHomming.png");

    @Override
    public ResourceLocation getModelResource(ProjectileHommingEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(ProjectileHommingEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(ProjectileHommingEntity animatable) {
        return null; // No animation file
    }
}
