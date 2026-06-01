package com.srp.client.renderer;

import com.srp.client.model.TendrilEsorModel;
import com.srp.entity.TendrilEsorEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TendrilEsorRenderer extends GeoEntityRenderer<TendrilEsorEntity> {

    public TendrilEsorRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TendrilEsorModel());
    }
}
