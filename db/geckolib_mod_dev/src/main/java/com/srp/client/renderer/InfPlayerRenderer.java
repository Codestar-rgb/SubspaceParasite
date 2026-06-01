package com.srp.client.renderer;

import com.srp.client.model.InfPlayerModel;
import com.srp.entity.InfPlayerEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfPlayerRenderer extends GeoEntityRenderer<InfPlayerEntity> {

    public InfPlayerRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfPlayerModel());
    }
}
