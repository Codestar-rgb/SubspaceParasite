package com.srp.client.renderer;

import com.srp.client.model.LumModel;
import com.srp.entity.LumEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LumRenderer extends GeoEntityRenderer<LumEntity> {

    public LumRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LumModel());
    }
}
