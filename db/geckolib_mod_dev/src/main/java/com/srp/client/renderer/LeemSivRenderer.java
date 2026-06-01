package com.srp.client.renderer;

import com.srp.client.model.LeemSivModel;
import com.srp.entity.LeemSivEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LeemSivRenderer extends GeoEntityRenderer<LeemSivEntity> {

    public LeemSivRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LeemSivModel());
    }
}
