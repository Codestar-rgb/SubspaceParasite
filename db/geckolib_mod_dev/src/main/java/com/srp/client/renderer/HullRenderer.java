package com.srp.client.renderer;

import com.srp.client.model.HullModel;
import com.srp.entity.HullEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class HullRenderer extends GeoEntityRenderer<HullEntity> {

    public HullRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new HullModel());
    }
}
