package com.srp.client.renderer;

import com.srp.client.model.NakModel;
import com.srp.entity.NakEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class NakRenderer extends GeoEntityRenderer<NakEntity> {

    public NakRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new NakModel());
    }
}
