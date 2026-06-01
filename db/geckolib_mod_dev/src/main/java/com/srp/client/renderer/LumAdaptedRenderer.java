package com.srp.client.renderer;

import com.srp.client.model.LumAdaptedModel;
import com.srp.entity.LumAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LumAdaptedRenderer extends GeoEntityRenderer<LumAdaptedEntity> {

    public LumAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LumAdaptedModel());
    }
}
