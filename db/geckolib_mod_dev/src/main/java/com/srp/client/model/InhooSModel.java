package com.srp.client.model;

import com.srp.entity.InhooSEntity;
import software.bernie.geckolib.model.GeoModel;
import net.minecraft.resources.ResourceLocation;

public class InhooSModel extends GeoModel<InhooSEntity> {

    private static final ResourceLocation MODEL = new ResourceLocation("srp", "geo/crude_inhooS.geo.json");
    private static final ResourceLocation TEXTURE = new ResourceLocation("srp", "textures/entity/crude_inhooS.png");
    private static final ResourceLocation ANIMATION = new ResourceLocation("srp", "animations/crude_inhooS.animation.json");

    @Override
    public ResourceLocation getModelResource(InhooSEntity animatable) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(InhooSEntity animatable) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(InhooSEntity animatable) {
        return ANIMATION;
    }
}
