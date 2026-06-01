package com.srp.client.renderer;

import com.srp.client.model.TendrilNoglaModel;
import com.srp.entity.TendrilNoglaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TendrilNoglaRenderer extends GeoEntityRenderer<TendrilNoglaEntity> {

    public TendrilNoglaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TendrilNoglaModel());
    }
}
