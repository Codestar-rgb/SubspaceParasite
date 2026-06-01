package com.srp.client.renderer;

import com.srp.client.model.AwakenedOroncoAwModel;
import com.srp.entity.AwakenedOroncoAwEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class AwakenedOroncoAwRenderer extends GeoEntityRenderer<AwakenedOroncoAwEntity> {

    public AwakenedOroncoAwRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new AwakenedOroncoAwModel());
    }
}
