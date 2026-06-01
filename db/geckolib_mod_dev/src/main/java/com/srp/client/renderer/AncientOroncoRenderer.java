package com.srp.client.renderer;

import com.srp.client.model.AncientOroncoModel;
import com.srp.entity.AncientOroncoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class AncientOroncoRenderer extends GeoEntityRenderer<AncientOroncoEntity> {

    public AncientOroncoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new AncientOroncoModel());
    }
}
