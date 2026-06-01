package com.srp.client.renderer;

import com.srp.client.model.RatholModel;
import com.srp.entity.RatholEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class RatholRenderer extends GeoEntityRenderer<RatholEntity> {

    public RatholRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new RatholModel());
    }
}
