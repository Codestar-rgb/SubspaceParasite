package com.srp.client.renderer;

import com.srp.client.model.TendrilBanoModel;
import com.srp.entity.TendrilBanoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TendrilBanoRenderer extends GeoEntityRenderer<TendrilBanoEntity> {

    public TendrilBanoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TendrilBanoModel());
    }
}
