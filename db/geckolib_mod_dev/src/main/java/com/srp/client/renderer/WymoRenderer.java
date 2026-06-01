package com.srp.client.renderer;

import com.srp.client.model.WymoModel;
import com.srp.entity.WymoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class WymoRenderer extends GeoEntityRenderer<WymoEntity> {

    public WymoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new WymoModel());
    }
}
