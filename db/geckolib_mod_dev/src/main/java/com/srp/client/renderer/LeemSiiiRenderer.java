package com.srp.client.renderer;

import com.srp.client.model.LeemSiiiModel;
import com.srp.entity.LeemSiiiEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class LeemSiiiRenderer extends GeoEntityRenderer<LeemSiiiEntity> {

    public LeemSiiiRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new LeemSiiiModel());
    }
}
