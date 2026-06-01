package com.srp.client.renderer;

import com.srp.client.model.PheonModel;
import com.srp.entity.PheonEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class PheonRenderer extends GeoEntityRenderer<PheonEntity> {

    public PheonRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new PheonModel());
    }
}
