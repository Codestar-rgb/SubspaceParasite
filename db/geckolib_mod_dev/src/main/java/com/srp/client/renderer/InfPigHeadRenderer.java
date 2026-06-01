package com.srp.client.renderer;

import com.srp.client.model.InfPigHeadModel;
import com.srp.entity.InfPigHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfPigHeadRenderer extends GeoEntityRenderer<InfPigHeadEntity> {

    public InfPigHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfPigHeadModel());
    }
}
