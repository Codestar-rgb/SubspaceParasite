package com.srp.client.renderer;

import com.srp.client.model.DorpaModel;
import com.srp.entity.DorpaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DorpaRenderer extends GeoEntityRenderer<DorpaEntity> {

    public DorpaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DorpaModel());
    }
}
