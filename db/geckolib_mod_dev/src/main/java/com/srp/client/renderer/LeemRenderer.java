package com.srp.client.renderer;

import com.srp.client.model.LeemModel;
import com.srp.entity.LeemEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LeemRenderer extends GeoEntityRenderer<LeemEntity> {

    public LeemRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LeemModel());
    }
}
