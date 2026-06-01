package com.srp.client.renderer;

import com.srp.client.model.TendrilCanraModel;
import com.srp.entity.TendrilCanraEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TendrilCanraRenderer extends GeoEntityRenderer<TendrilCanraEntity> {

    public TendrilCanraRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TendrilCanraModel());
    }
}
