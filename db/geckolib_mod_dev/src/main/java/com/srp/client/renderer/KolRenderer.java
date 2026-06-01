package com.srp.client.renderer;

import com.srp.client.model.KolModel;
import com.srp.entity.KolEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class KolRenderer extends GeoEntityRenderer<KolEntity> {

    public KolRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new KolModel());
    }
}
