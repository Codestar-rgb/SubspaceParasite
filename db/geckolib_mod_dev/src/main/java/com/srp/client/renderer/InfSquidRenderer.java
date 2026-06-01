package com.srp.client.renderer;

import com.srp.client.model.InfSquidModel;
import com.srp.entity.InfSquidEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfSquidRenderer extends GeoEntityRenderer<InfSquidEntity> {

    public InfSquidRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfSquidModel());
    }
}
