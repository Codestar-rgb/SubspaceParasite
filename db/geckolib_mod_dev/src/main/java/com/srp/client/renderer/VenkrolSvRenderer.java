package com.srp.client.renderer;

import com.srp.client.model.VenkrolSvModel;
import com.srp.entity.VenkrolSvEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class VenkrolSvRenderer extends GeoEntityRenderer<VenkrolSvEntity> {

    public VenkrolSvRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new VenkrolSvModel());
    }
}
