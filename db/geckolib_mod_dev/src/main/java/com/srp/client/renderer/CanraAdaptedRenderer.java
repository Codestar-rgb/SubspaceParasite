package com.srp.client.renderer;

import com.srp.client.model.CanraAdaptedModel;
import com.srp.entity.CanraAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class CanraAdaptedRenderer extends GeoEntityRenderer<CanraAdaptedEntity> {

    public CanraAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new CanraAdaptedModel());
    }
}
