package com.srp.client.renderer;

import com.srp.client.model.TendrilDragonElwModel;
import com.srp.entity.TendrilDragonElwEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TendrilDragonElwRenderer extends GeoEntityRenderer<TendrilDragonElwEntity> {

    public TendrilDragonElwRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TendrilDragonElwModel());
    }
}
