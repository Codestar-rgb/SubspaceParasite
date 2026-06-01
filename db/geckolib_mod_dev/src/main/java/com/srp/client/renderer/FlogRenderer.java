package com.srp.client.renderer;

import com.srp.client.model.FlogModel;
import com.srp.entity.FlogEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FlogRenderer extends GeoEntityRenderer<FlogEntity> {

    public FlogRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FlogModel());
    }
}
