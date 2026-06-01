package com.srp.client.renderer;

import com.srp.client.model.VenkrolSiiiModel;
import com.srp.entity.VenkrolSiiiEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class VenkrolSiiiRenderer extends GeoEntityRenderer<VenkrolSiiiEntity> {

    public VenkrolSiiiRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new VenkrolSiiiModel());
    }
}
