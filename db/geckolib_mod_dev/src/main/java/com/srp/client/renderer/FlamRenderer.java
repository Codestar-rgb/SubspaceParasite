package com.srp.client.renderer;

import com.srp.client.model.FlamModel;
import com.srp.entity.FlamEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FlamRenderer extends GeoEntityRenderer<FlamEntity> {

    public FlamRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FlamModel());
    }
}
