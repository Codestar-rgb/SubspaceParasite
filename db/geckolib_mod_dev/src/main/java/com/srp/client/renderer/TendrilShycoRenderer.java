package com.srp.client.renderer;

import com.srp.client.model.TendrilShycoModel;
import com.srp.entity.TendrilShycoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TendrilShycoRenderer extends GeoEntityRenderer<TendrilShycoEntity> {

    public TendrilShycoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TendrilShycoModel());
    }
}
