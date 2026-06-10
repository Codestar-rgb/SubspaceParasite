package com.example.srparasites.client.model;

import net.minecraft.resources.ResourceLocation;
import net.minecraft.client.renderer.RenderType;
import software.bernie.geckolib.model.GeoModel;
import com.example.srparasites.entity.KirinEntity;

public class KirinGeoModel extends GeoModel<KirinEntity> {
    @Override
    public ResourceLocation getModelResource(KirinEntity animatable) {
        return new ResourceLocation("srparasites", "geo/entity/kirin.geo.json");
    }

    @Override
    public ResourceLocation getTextureResource(KirinEntity animatable) {
        return new ResourceLocation("srparasites", "textures/entity/monster/kirin.png");
    }

    @Override
    public ResourceLocation getAnimationResource(KirinEntity animatable) {
        return new ResourceLocation("srparasites", "animations/entity/kirin.animation.json");
    }

    // Animation layer registrations
    // Layer: base - type: base, priority: 0, bones: 39
    // For Class A-2 movement-driven animations, override codeAnimations:
    // @Override
    // public void codeAnimations(KirinEntity animatable, AnimatableManager<KirinEntity> manager) {
    //     // Insert movement-driven animation code here
    // }
}
