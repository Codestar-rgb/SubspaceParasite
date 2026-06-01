package com.srp.client.renderer;

import com.srp.client.model.LeemBModel;
import com.srp.entity.LeemBEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LeemBRenderer extends GeoEntityRenderer<LeemBEntity> {

    public LeemBRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LeemBModel());
    }
}
