package com.srp.client.renderer;

import com.srp.client.model.InfEndermanHeadModel;
import com.srp.entity.InfEndermanHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfEndermanHeadRenderer extends GeoEntityRenderer<InfEndermanHeadEntity> {

    public InfEndermanHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfEndermanHeadModel());
    }
}
