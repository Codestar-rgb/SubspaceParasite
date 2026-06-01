package com.srp.client.renderer;

import com.srp.client.model.BanoAdaptedModel;
import com.srp.entity.BanoAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class BanoAdaptedRenderer extends GeoEntityRenderer<BanoAdaptedEntity> {

    public BanoAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new BanoAdaptedModel());
    }
}
