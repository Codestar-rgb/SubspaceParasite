package com.srp.client.renderer;

import com.srp.client.model.VenkrolSivModel;
import com.srp.entity.VenkrolSivEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class VenkrolSivRenderer extends GeoEntityRenderer<VenkrolSivEntity> {

    public VenkrolSivRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new VenkrolSivModel());
    }
}
