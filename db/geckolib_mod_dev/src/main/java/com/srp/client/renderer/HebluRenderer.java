package com.srp.client.renderer;

import com.srp.client.model.HebluModel;
import com.srp.entity.HebluEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class HebluRenderer extends GeoEntityRenderer<HebluEntity> {

    public HebluRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new HebluModel());
    }
}
