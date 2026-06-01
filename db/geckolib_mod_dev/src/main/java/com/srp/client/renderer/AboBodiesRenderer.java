package com.srp.client.renderer;

import com.srp.client.model.AboBodiesModel;
import com.srp.entity.AboBodiesEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class AboBodiesRenderer extends GeoEntityRenderer<AboBodiesEntity> {

    public AboBodiesRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new AboBodiesModel());
    }
}
