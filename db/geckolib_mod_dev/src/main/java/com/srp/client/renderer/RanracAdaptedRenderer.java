package com.srp.client.renderer;

import com.srp.client.model.RanracAdaptedModel;
import com.srp.entity.RanracAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class RanracAdaptedRenderer extends GeoEntityRenderer<RanracAdaptedEntity> {

    public RanracAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new RanracAdaptedModel());
    }
}
