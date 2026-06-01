package com.srp.client.renderer;

import com.srp.client.model.KirinModel;
import com.srp.entity.KirinEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class KirinRenderer extends GeoEntityRenderer<KirinEntity> {

    public KirinRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new KirinModel());
    }
}
