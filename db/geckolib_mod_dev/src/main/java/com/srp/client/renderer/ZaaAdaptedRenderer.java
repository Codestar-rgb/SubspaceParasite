package com.srp.client.renderer;

import com.srp.client.model.ZaaAdaptedModel;
import com.srp.entity.ZaaAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class ZaaAdaptedRenderer extends GeoEntityRenderer<ZaaAdaptedEntity> {

    public ZaaAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new ZaaAdaptedModel());
    }
}
