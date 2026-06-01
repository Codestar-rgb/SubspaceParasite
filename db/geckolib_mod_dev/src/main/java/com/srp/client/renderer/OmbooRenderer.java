package com.srp.client.renderer;

import com.srp.client.model.OmbooModel;
import com.srp.entity.OmbooEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class OmbooRenderer extends GeoEntityRenderer<OmbooEntity> {

    public OmbooRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new OmbooModel());
    }
}
