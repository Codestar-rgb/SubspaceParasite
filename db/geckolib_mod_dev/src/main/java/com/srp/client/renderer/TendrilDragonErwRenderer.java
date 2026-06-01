package com.srp.client.renderer;

import com.srp.client.model.TendrilDragonErwModel;
import com.srp.entity.TendrilDragonErwEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TendrilDragonErwRenderer extends GeoEntityRenderer<TendrilDragonErwEntity> {

    public TendrilDragonErwRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TendrilDragonErwModel());
    }
}
