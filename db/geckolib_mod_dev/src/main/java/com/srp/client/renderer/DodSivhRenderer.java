package com.srp.client.renderer;

import com.srp.client.model.DodSivhModel;
import com.srp.entity.DodSivhEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DodSivhRenderer extends GeoEntityRenderer<DodSivhEntity> {

    public DodSivhRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DodSivhModel());
    }
}
