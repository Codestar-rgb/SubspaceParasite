package com.srp.client.renderer;

import com.srp.client.model.TendrilModel;
import com.srp.entity.TendrilEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TendrilRenderer extends GeoEntityRenderer<TendrilEntity> {

    public TendrilRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TendrilModel());
    }
}
