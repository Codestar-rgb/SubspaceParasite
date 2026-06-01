package com.srp.client.renderer;

import com.srp.client.model.HullAdaptedModel;
import com.srp.entity.HullAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class HullAdaptedRenderer extends GeoEntityRenderer<HullAdaptedEntity> {

    public HullAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new HullAdaptedModel());
    }
}
