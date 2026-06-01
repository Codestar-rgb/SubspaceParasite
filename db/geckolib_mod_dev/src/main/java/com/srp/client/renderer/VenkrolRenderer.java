package com.srp.client.renderer;

import com.srp.client.model.VenkrolModel;
import com.srp.entity.VenkrolEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class VenkrolRenderer extends GeoEntityRenderer<VenkrolEntity> {

    public VenkrolRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new VenkrolModel());
    }
}
