package com.srp.client.renderer;

import com.srp.client.model.TerlaModel;
import com.srp.entity.TerlaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TerlaRenderer extends GeoEntityRenderer<TerlaEntity> {

    public TerlaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TerlaModel());
    }
}
