package com.srp.client.renderer;

import com.srp.client.model.TendrilAngedModel;
import com.srp.entity.TendrilAngedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TendrilAngedRenderer extends GeoEntityRenderer<TendrilAngedEntity> {

    public TendrilAngedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TendrilAngedModel());
    }
}
