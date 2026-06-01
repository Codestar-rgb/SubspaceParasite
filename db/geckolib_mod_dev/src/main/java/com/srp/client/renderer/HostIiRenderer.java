package com.srp.client.renderer;

import com.srp.client.model.HostIiModel;
import com.srp.entity.HostIiEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class HostIiRenderer extends GeoEntityRenderer<HostIiEntity> {

    public HostIiRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new HostIiModel());
    }
}
