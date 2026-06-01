package com.srp.client.renderer;

import com.srp.client.model.InfectedInfDragonEModel;
import com.srp.entity.InfectedInfDragonEEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfectedInfDragonERenderer extends GeoEntityRenderer<InfectedInfDragonEEntity> {

    public InfectedInfDragonERenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfectedInfDragonEModel());
    }
}
