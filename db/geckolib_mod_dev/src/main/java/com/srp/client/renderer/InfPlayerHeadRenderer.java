package com.srp.client.renderer;

import com.srp.client.model.InfPlayerHeadModel;
import com.srp.entity.InfPlayerHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfPlayerHeadRenderer extends GeoEntityRenderer<InfPlayerHeadEntity> {

    public InfPlayerHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfPlayerHeadModel());
    }
}
