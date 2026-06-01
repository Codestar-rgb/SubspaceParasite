package com.srp.client.renderer;

import com.srp.client.model.RanracModel;
import com.srp.entity.RanracEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class RanracRenderer extends GeoEntityRenderer<RanracEntity> {

    public RanracRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new RanracModel());
    }
}
