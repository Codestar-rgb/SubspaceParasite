package com.srp.client.renderer;

import com.srp.client.model.InfDragonEModel;
import com.srp.entity.InfDragonEEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfDragonERenderer extends GeoEntityRenderer<InfDragonEEntity> {

    public InfDragonERenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfDragonEModel());
    }
}
