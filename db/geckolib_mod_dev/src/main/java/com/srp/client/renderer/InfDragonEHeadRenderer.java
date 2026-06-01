package com.srp.client.renderer;

import com.srp.client.model.InfDragonEHeadModel;
import com.srp.entity.InfDragonEHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfDragonEHeadRenderer extends GeoEntityRenderer<InfDragonEHeadEntity> {

    public InfDragonEHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfDragonEHeadModel());
    }
}
