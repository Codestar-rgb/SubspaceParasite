package com.srp.client.renderer;

import com.srp.client.model.HeedModel;
import com.srp.entity.HeedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class HeedRenderer extends GeoEntityRenderer<HeedEntity> {

    public HeedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new HeedModel());
    }
}
