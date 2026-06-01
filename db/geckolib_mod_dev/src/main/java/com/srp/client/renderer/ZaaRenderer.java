package com.srp.client.renderer;

import com.srp.client.model.ZaaModel;
import com.srp.entity.ZaaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class ZaaRenderer extends GeoEntityRenderer<ZaaEntity> {

    public ZaaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new ZaaModel());
    }
}
