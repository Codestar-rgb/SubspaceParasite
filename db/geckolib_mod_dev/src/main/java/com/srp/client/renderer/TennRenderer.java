package com.srp.client.renderer;

import com.srp.client.model.TennModel;
import com.srp.entity.TennEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TennRenderer extends GeoEntityRenderer<TennEntity> {

    public TennRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TennModel());
    }
}
