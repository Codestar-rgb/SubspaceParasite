package com.srp.client.renderer;

import com.srp.client.model.InfectedInfPlayerModel;
import com.srp.entity.InfectedInfPlayerEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfectedInfPlayerRenderer extends GeoEntityRenderer<InfectedInfPlayerEntity> {

    public InfectedInfPlayerRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfectedInfPlayerModel());
    }
}
