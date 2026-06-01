package com.srp.client.renderer;

import com.srp.client.model.VenkrolSiiModel;
import com.srp.entity.VenkrolSiiEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class VenkrolSiiRenderer extends GeoEntityRenderer<VenkrolSiiEntity> {

    public VenkrolSiiRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new VenkrolSiiModel());
    }
}
