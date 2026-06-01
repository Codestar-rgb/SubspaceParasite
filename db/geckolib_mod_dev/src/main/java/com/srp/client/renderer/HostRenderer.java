package com.srp.client.renderer;

import com.srp.client.model.HostModel;
import com.srp.entity.HostEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class HostRenderer extends GeoEntityRenderer<HostEntity> {

    public HostRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new HostModel());
    }
}
