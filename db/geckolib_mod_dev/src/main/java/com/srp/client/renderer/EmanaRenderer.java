package com.srp.client.renderer;

import com.srp.client.model.EmanaModel;
import com.srp.entity.EmanaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class EmanaRenderer extends GeoEntityRenderer<EmanaEntity> {

    public EmanaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new EmanaModel());
    }
}
