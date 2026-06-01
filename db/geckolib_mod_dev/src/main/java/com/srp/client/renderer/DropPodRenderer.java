package com.srp.client.renderer;

import com.srp.client.model.DropPodModel;
import com.srp.entity.DropPodEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DropPodRenderer extends GeoEntityRenderer<DropPodEntity> {

    public DropPodRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DropPodModel());
    }
}
