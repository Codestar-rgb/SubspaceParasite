package com.srp.client.model;

import com.srp.entity.InhooMEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InhooMModel extends GeoModel<InhooMEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_inhooM.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_inhooM.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_inhooM.animation.json");

    @Override
    public ResourceLocation getModelResource(InhooMEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InhooMEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InhooMEntity animatable) {
        return ANIMATION;
    }
}
